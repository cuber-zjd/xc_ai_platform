from typing import Optional
from sqlmodel import SQLModel, Field
from app.models.base import BaseDBModel

class SysPostBase(SQLModel):
    sync_id: Optional[str] = Field(default=None, index=True, description="Original ID (postno)")
    name: str = Field(index=True, description="Post Name (postname)")
    code: Optional[str] = Field(default=None, description="Post Code (postno)")
    dept_id: Optional[str] = Field(default=None, index=True, description="Belonging Dept ID (dept_id)")

class SysPost(BaseDBModel, SysPostBase, table=True):
    __tablename__ = "sys_post"
