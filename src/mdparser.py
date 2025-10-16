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

    def into_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "doc": self.doc,
            "presence": self.presence,
        }

   
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
                "field {} has different types in different responses ({} and {})",
                k, f.type, v.type
            )

        # union the nested response if not primitive data
        if f.type != "data":
            if f.nested is None or v.nested is None:
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
        return {
            "name": self.name,
            "doc": self.doc,
            "scope": self.scope,
            "version": self.version,
            "permissions": self.permissions,
            "params": [p.into_dict() for p in self.params],
            "sample_params": self.sample_params,
            "success_response": self.success_response.into_dict(),
            "error_response": self.error_response.into_dict(),
        }

    
def parse_request_name(s: str) -> str:
    s = s.replace("*", "")
    return s.strip()


def parse_version(s: str) -> int:
    if s != "3":
        raise ParseError("other api versions not supported: {}", s)

    return 3


# expects the type value including the square brackets
def parse_param_type(s: str) -> str:
    if len(s) < 2 or s[0] != "[" or s[-1] != "]":
        raise ParseError("expected type to be '[type]': '{}'", s)

    match s[1:-1]:
        case "boolean":
            return "bool"
        case "date":
            return "date"
        case "number":
            return "int"
        case "num":
            return "int"
        case "string":
            return "str"
        case "time": 
            return "time" # datetime.time
        case "timestamp yyyy-MM-dd HH:mm:ss.SSS":
            return "datetime" # datetime.datetime
        case _:
            raise ParseError("unknown type: {}", s)
        

def parse_param_line(s: str, presence: str) -> Parameter:
    param = Parameter()

    if presence == "conditional":
        param.name = ""
        param.type = ""
        param.doc = s
        param.presence = "conditional"
        return param
    
    if presence != "required" and presence != "optional":
        raise ParseError("unknown presence val: '{}'", presence)
    param.presence = presence 

    if s[0] != "`":
        raise ParseError("expeced param line to start with backtick: '{}'", s)

    defin, match, descr = s[1:].partition("` - ")
    if match == "":
        raise ParseError("expected param line to contain 1 '` - ': '{}'", s)

    param.doc = descr

    name, match, type = defin.partition(" ")
    if match != "":
        param.type = parse_param_type(type)
    else:
        param.type = ""
        
    param.name = name
    return param


def parse_params(s: str) -> list[Parameter]:
    spl = re.split(empty_line_re, s)
    lines = [l.strip() for l in spl]

    params = []
    presence = None
    
    for l in lines:
        logger.debug(l)
        if l.startswith("**"):
            presence = l.replace("*", "").replace(":","").lower()
            
            match presence:
                case "required" | "optional" | "conditional":
                    continue
                case _:
                    raise ParseError("unknown presence {}", presence)

        if presence is None:
            raise ParseError("unknown presence for line {}", l)

        if l.lower() == "none":
            continue
        
        params.append(parse_param_line(l, presence))

    return params


def resp_from_json_obj(o: dict) -> Response:
    resp = Response()

    for k, v in o.items():
        if isinstance(v, dict):
            f = ResponseField(k, "object", resp_from_json_obj(v))
            resp.fields[k] = f
            continue
        if isinstance(v, list):
            f = ResponseField(k, "array", resp_from_json_array(v))
            resp.fields[k] = f
            continue

        resp.fields[k] = ResponseField(k, "data", None)

    return resp


def resp_from_json_array(a: list) -> Response:
    resp = Response()

    for o in a:
        if not isinstance(o, dict):
            raise ParseError("expecting array to only contain objects, got {}", type(o))
        resp = union_response(resp, resp_from_json_obj(o))

    return resp


def parse_json_response(s: str) -> Response:
    try:
        decoded = json.loads(s)
        if isinstance(decoded, dict):
            return resp_from_json_obj(decoded)
        elif isinstance(decoded, list):
            return resp_from_json_array(decoded)
        else:
            raise ParseError("expected list or dict, got: {}", type(decoded))
    except (ParseError, ValueError, json.JSONDecodeError) as err:
        logger.error(f"json is:\n{s}")
        raise ParseError("could not parse success json") from err
    

def parse_success_response(s: str) -> Response:
    _, match, rest = s.partition("```javascript\n")
    if match == "":
        _, match, rest = s.partition("```json\n")
        if match == "":
            raise ParseError("could not find start of js code block")

    json_str, match, _ = rest.partition("```")
    if match == "":
        raise ParseError("could not find end of js code block")

    return parse_json_response(json_str)


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

        res = union_response(res, parse_json_response(json_str))
    
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
            case "params":
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



