from typing import Protocol, TypeVar
from pydantic import BaseModel
T = TypeVar("T", bound=BaseModel)

class Provider(Protocol):
    def generate(self, agent: str, schema: type[T], context: dict) -> T: ...
