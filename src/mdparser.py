from typing import Literal, Optional
import logging
import json
import re

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

header_re = r"\* +\*\*"
empty_line_re = r"\n\s*\n"


class ParseError(Exception):
    pass


class Parameter:
    name: str
    type: str
    doc: str
    presence: Literal["required", "optional", "conditional"]

    def __init__(self):
        self.name = ""
        self.type = ""
        self.doc = ""
        self.presence = ""

    def __str__(self) -> str:
        return f"{self.presence}: {self.name} [{self.type}] - {self.doc}\n"

    def into_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "doc": self.doc,
            "presence": self.presence,
        }


# a response field with type "array" that has no "nested" field is an
# array of primitives
class ResponseField:
    key: str
    type: Literal["data", "array", "object"]
    nested: Optional["Response"]

    def __init__(
            self,
            key: str,
            type: Literal["data", "array", "object"],
            nested: Optional["Response"]
    ):
        self.key = key
        self.type = type
        self.nested = nested

    def __str__(self) -> str:
        has_nested = "No"
        if self.nested is not None:
            has_nested = "Yes"
        return f"ResponseField key: {self.key}, " \
            f"type: {self.type}, " \
            f"has nested: {has_nested}"

    def into_dict(self) -> dict:
        d = {
            "key": self.key,
            "type": self.type,
            "nested": None,
        }

        if self.nested is not None:
            logger.debug(f"nested is not none: {self.nested}")
            d["nested"] = self.nested.into_dict()

        return d


class Response:
    fields: dict[str, ResponseField]

    def __init__(self):
        self.fields = {}

    def str_indent(self, indent: int) -> str:
        spaces = " " * indent
        s = ""
        for f in self.fields.values():
            s = f"{spaces}{f.key} [{f.type}]\n"
            if f.nested is not None:
                s += f.nested.str_indent(indent+2)
        return s + "\n"

    def __str__(self):
        return self.str_indent(0)

    def into_dict(self) -> dict:
        return {
            "fields": {
                k: f.into_dict() for k, f in self.fields.items()
            }
        }


def union_response(r1: Response, r2: Response) -> Response:
    res = Response()

    for k, v in r1.fields.items():
        res.fields[k] = v

    for k, v in r2.fields.items():
        f = res.fields.get(k)
        if f is None:
            res.fields[k] = v
            continue

        if f.type != v.type:
            raise ValueError(
                "field {} has conflicting types ({} and {})",
                k, f.type, v.type
            )

        # union the nested response if not primitive data
        if f.type != "data":
            if f.nested is None or v.nested is None:
                if f.type == "array":
                    continue
                raise ValueError("ResponseField has missing nested type")
            res.fields[k].nested = union_response(f.nested, v.nested)

    return res


class Request:
    name: str
    doc: str
    scope: str
    version: int
    permissions: str
    params: list[Parameter]
    sample_params: str
    success_response: Response
    error_response: Response

    def into_dict(self) -> dict:
        req = {
            "name": self.name,
            "doc": self.doc,
            "scope": self.scope,
            "version": self.version,

            "params": [p.into_dict() for p in self.params],
            "sample_params": self.sample_params,
            "success_response": self.success_response.into_dict(),
            "error_response": self.error_response.into_dict(),
        }

        # permissions might not be set in v2 apis
        if hasattr(self, "permissions"):
            req["permissions"] = self.permissions,

        return req

    def __str__(self) -> str:
        s = f"name: {self.name}\n" \
            f"doc: {self.doc}\n" \
            f"scope: {self.scope}\n" \
            f"version: {self.version}\n"
        if hasattr(self, "permissions"):
            s += f"permissions: {self.permissions}\n"

        s += f"params:\n\t{"\t".join([str(p) for p in self.params])}\n" \
            f"sample_params: {self.sample_params}\n" \
            f"success_response: {self.success_response}\n" \
            f"error_response: {self.error_response}\n"

        return s


def parse_request_name(s: str) -> str:
    s = s.replace("*", "")
    return s.strip()


def parse_version(s: str) -> int:
    match s:
        case "1":
            raise ParseError("v1 apis not supported")
        case "2":
            return 2
        case "3":
            return 3
        case _:
            raise ParseError("unknown api version: '{}'", s)


# expects the type value including the square brackets
def parse_param_type(s: str) -> str:
    if len(s) < 2 or s[0] != "[" or s[-1] != "]":
        raise ParseError("expected type to be '[type]': '{}'", s)

    type_str = s[1:-1]
    match type_str:
        case 'integer or "all"':
            return "any"
        case "boolean":
            return "bool"
        case "date" | "date dd/mm/yyyy":
            return "date"
        case "timestamp yyyy-MM-dd HH:mm:ss.SSS":
            return "datetime"  # datetime.datetime
        case "decimal":
            return "float"
        case "number" | "num" | "integer":
            return "int"
        case "array":
            return "list"  # would be nice to include the type
        case "string":
            return "str"
        case "time":
            return "time"  # datetime.time

        case _:
            raise ParseError("unknown type: {}", type_str)


def parse_param_line(s: str, presence: str) -> Parameter:
    param = Parameter()

    if presence == "conditional":
        param.doc = s
        param.presence = "conditional"
        return param

    if presence != "required" and presence != "optional":
        raise ParseError("unknown presence val: '{}'", presence)
    param.presence = presence

    if s[0] != "`":
        raise ParseError("expeced param line to start with backtick: '{}'", s)

    defin, match, descr = s[1:].partition("` - ")
    if match != "":
        param.doc = descr

    name, match, type = defin.replace("`", "").partition(" ")
    if match != "":
        param.type = parse_param_type(type.strip())

    param.name = name
    return param


def parse_params(s: str) -> list[Parameter]:
    spl = re.split(empty_line_re, s)
    lines = [line.strip() for line in spl]

    params = []
    presence = None

    for line in lines:
        logger.debug(line)
        if line.startswith("**"):
            presence = line.replace("*", "").replace(":", "").lower()

            match presence:
                case "required" | "optional" | "conditional":
                    continue
                case _:
                    raise ParseError("unknown presence {}", presence)

        if presence is None:
            raise ParseError("unknown presence for line {}", line)

        if line.lower() == "none":
            continue

        params.append(parse_param_line(line, presence))

    return params


def res_from_json_obj(o: dict) -> Response:
    res = Response()

    for k, v in o.items():
        if isinstance(v, dict):
            f = ResponseField(k, "object", res_from_json_obj(v))
            res.fields[k] = f
            continue
        if isinstance(v, list):
            res.fields[k] = res_field_from_json_array(k, v)
            continue

        res.fields[k] = ResponseField(k, "data", None)

    return res


def res_field_from_json_array(key: str, a: list) -> ResponseField:
    f = ResponseField(key, "array", None)

    types = {type(e).__name__ for e in a}
    if len(types) != 1:
        raise ParseError(
            "array has too many types: {}", ",".join(types)
        )

    t = list(types)[0]
    if t == "str" or t == "int":
        return f

    if t != "dict":
        raise ParseError("unsupported array type: {}", t)

    nested = Response()
    for o in a:
        nested = union_response(nested, res_from_json_obj(o))

    f.nested = nested
    return f


def parse_json_response(s: str) -> Response:
    try:
        decoded = json.loads(s)
        if isinstance(decoded, dict):
            return res_from_json_obj(decoded)
        else:
            raise ParseError(
                "expected while json to be a dict, got: {}", type(decoded))
    except (ParseError, ValueError, json.JSONDecodeError) as err:
        logger.error(f"json is:\n{s}")
        raise ParseError("could not parse json response") from err


def parse_success_response(s: str) -> Response:
    _, match, rest = s.partition("```javascript\n")
    if match == "":
        _, match, rest = s.partition("```json\n")
        if match == "":
            raise ParseError("could not find start of js code block")

    json_str, match, _ = rest.partition("```")
    if match == "":
        raise ParseError("could not find end of js code block")

    try:
        return parse_json_response(json_str)
    except ParseError as err:
        raise ParseError("could not parse success response") from err


def parse_error_response(s: str) -> Response:
    res = Response()

    # tass have left out quotes for many of their err responses so add
    # them back in
    s = s.replace("__invalid:", '"__invalid":')
    while True:
        _, match, rest = s.partition("```javascript\n")
        if match == "":
            _, match, rest = s.partition("```json\n")
            if match == "":
                break

        json_str, match, s = rest.partition("```")
        if match == "":
            raise ParseError("could not find end of js code block")

        json_str = json_str.strip()
        if len(json_str) < 2:
            raise ParseError("stripped js code block empty: {}", json_str)

        # tass have also left out object curly brackets on these
        # definitions
        if json_str[0] != "{":
            json_str = "{" + json_str + "}"
        try:
            res = union_response(res, parse_json_response(json_str))
        except ParseError as err:
            logger.error(f"failed error response is:\n{json_str}")
            raise ParseError("could not parse error response") from err

    return res


def parse_request(text: str, api_scope: str) -> Request:
    req = Request()
    req.scope = api_scope
    title, match, text = text.partition("----")
    if match == "":
        raise ParseError("could not find title line")

    logger.debug("parsing req name")
    req.name = parse_request_name(title)

    logger.debug("parsing req doc")
    split = re.split(header_re, text)
    desc = split[0].strip()
    if "**:" in desc:
        raise ParseError("seems as if req has no documentation")
    req.doc = desc

    for spl in split[1:]:
        header, match, body = spl.partition(":**")
        if match == "":
            raise ParseError("text is malformed at header split: {}", spl)

        logger.debug(f"header is '{header}'")
        match header.lower():
            case "version history":
                logger.debug("parsing version history")
                pass
            case "version":
                logger.debug("parsing version")
                req.version = parse_version(body.strip())
            case "permission":
                logger.debug("parsing permission")
                req.permissions = body.strip()
            case "method":
                logger.debug("parsing method")
                pass
            case "params" | "parameters":
                logger.debug("parsing params")
                req.params = parse_params(body.strip())
            case "success response":
                logger.debug("parsing success response")
                req.success_response = parse_success_response(body.strip())
            case "error response":
                logger.debug("parsing error response")
                req.error_response = parse_error_response(body.strip())
            case "sample parameters":
                logger.debug("parsing sample params")
                req.sample_params = body.strip()
            case "sample get":
                logger.debug("parsing sample get")
                pass
            case "sample post":
                logger.debug("parsing sample post")
                pass
            case _:
                raise ParseError("unknown header: {}", header)

    return req
