from typing import Optional
from sqlmodel import SQLModel

class UserRead(SQLModel):
    id: int | str
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str = "user"
    avatar: Optional[str] = None
    dept_id: Optional[str] = None
    status: int
    is_superuser: bool = False

class UserCreate(SQLModel):
    username: str
    password: str
    full_name: str
    email: Optional[str] = None
    dept_id: Optional[str] = None
    is_superuser: bool = False
    status: int = 1

class UserUpdate(SQLModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    dept_id: Optional[str] = None
    password: Optional[str] = None
    is_superuser: Optional[bool] = None
    status: Optional[int] = None
