from typing import TextIO, TypeVar, Generic
from abc import ABC, abstractmethod

Res = TypeVar("Res") # Response Type

class TassRequest(Generic[Res], ABC):
    @abstractmethod
    def json() -> str:
        pass


class TassConnection:
    def send(self, request: TassRequest[Res]) -> Res:
        ...
    
class StudentDetailsResponse():
    ...

class StudentDetailsRequest(TassRequest):
    ...
