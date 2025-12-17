from typing import Generic, TypeVar, List
from pydantic import BaseModel

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    """
    Standard Pagination Model
    """
    total: int
    items: List[T]
    page: int
    size: int

    @classmethod
    def create(cls, items: List[T], total: int, page: int, size: int) -> "Page[T]":
        return cls(items=items, total=total, page=page, size=size)
