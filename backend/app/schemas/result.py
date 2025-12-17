from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel

T = TypeVar("T")

class Result(BaseModel, Generic[T]):
    """
    Unified Response Model
    """
    code: int
    msg: str
    data: Optional[T] = None

    @classmethod
    def success(cls, data: T = None, msg: str = "Success") -> "Result[T]":
        return cls(code=200, msg=msg, data=data)

    @classmethod
    def fail(cls, code: int = 500, msg: str = "Internal Server Error", data: Any = None) -> "Result[T]":
        return cls(code=code, msg=msg, data=data)
