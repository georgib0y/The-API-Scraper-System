from typing import Optional, Tuple
import logging 

logger = logging.getLogger(__name__)

class ParseError(Exception):
    pass


class Parameter:
    name: str
    presence: str # "required" | "optional" | "conditional"

    
class ResponseField:
    key: str
    value_type: str # "data" | "array" | "object"
    nested: Optional["Response"]


class Response:
    field: list[ResponseField]


class Request:
    action: str
    resource: str
    scope: str
    version: int
    permissions: str
    parameters: list[Parameter]
    success_response: Response
    error_response: Response


def parse_request_name(s: str) -> Tuple[str, str]:
    spl = s.split("**")
    if len(spl) != 1:
        raise ParseError("could not parse req name: {}", s)

    cap_idx = None
    for idx, c in enumerate(s):
        if c.isupper():
            cap_idx = idx
            break
    if cap_idx is None:
        raise ParseError("could not parse req name: {}", s)

    action = s[:cap_idx]
    resource = s[cap_idx:]
    if len(action) == 0 or len(resource) == 0:
        raise ParseError("could not parse req name: {}", s)
    
    return action, resource


def parse_version(s: str) -> int:
    if s != "3":
        raise ParseError("other api versions not supported: {}", s)

    return 3


def parse_params(s: str) -> list[Parameter]:
    ...


def parse_success_response(s: str) -> Response:
    ...


def parse_error_response(s: str) -> Response:
    ...


def parse_request(text: str) -> Request:
    req = Request()

    name, match, text = text.partition("----")
    if match == "":
        raise ParseError("could not match header line")
    
    req.action, req.resource = parse_request_name(name)

    for spl in text.split("* **"):
        header, match, body = spl.partition(":**")
        if match is None:
            raise ParseError("text is malformed at header split: {}", spl)
        match header:
            case "Version History":
                pass
            case "Version":
                req.version = parse_version(body.strip())
            case "Permission":
                pass
            case "Method":
                pass
            case "Params":
                req.parameters = parse_params(body.strip())
            case "Success Response":
                req.success_response = parse_success_response(body.strip())
            case "Error Response":
                req.success_response = parse_error_response(body.strip())
            case "Sample Parameters":
                pass
            case "Sample GET":
                pass
            case "Sample POST":
                pass
            case _:
                raise ParseError("unknown header: {}", header)
            
    return req
