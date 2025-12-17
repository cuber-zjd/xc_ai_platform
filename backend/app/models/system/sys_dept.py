from typing import Optional
from sqlmodel import SQLModel, Field
from app.models.base import BaseDBModel

class SysDeptBase(SQLModel):
    sync_id: Optional[str] = Field(default=None, index=True, description="Original ID (deptid)")
    name: str = Field(index=True, description="Dept Name (detpname)")
    code: Optional[str] = Field(default=None, description="Dept Code (dept_code)")
    parent_id: Optional[str] = Field(default=None, description="Parent Dept ID (parentid)")
    company_id: Optional[str] = Field(default=None, index=True, description="Belonging Company ID (rootparentid)")
    order: Optional[int] = Field(default=0, description="Display Order (orderindex)")

class SysDept(BaseDBModel, SysDeptBase, table=True):
    __tablename__ = "sys_dept"
