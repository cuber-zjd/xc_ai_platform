from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

class SysDeptBase(SQLModel):
    sync_id: Optional[str] = Field(default=None, index=True, description="Original ID (deptid)")
    name: str = Field(index=True, description="Dept Name (detpname)")
    code: Optional[str] = Field(default=None, description="Dept Code (dept_code)")
    parent_id: Optional[str] = Field(default=None, description="Parent Dept ID (parentid)")
    company_id: Optional[str] = Field(default=None, index=True, description="Belonging Company ID (rootparentid)")
    order: Optional[int] = Field(default=0, description="Display Order (orderindex)")
    
    status: int = Field(default=1, description="Status: 1=Normal, 0=Deleted")
    comment: Optional[str] = Field(default=None, description="Remarks")

class SysDept(SysDeptBase, table=True):
    __tablename__ = "sys_dept"
    
    id: int | None = Field(default=None, primary_key=True)
    create_time: datetime = Field(default_factory=datetime.now)
    update_time: datetime = Field(default_factory=datetime.now)
    create_by: Optional[str] = Field(default=None)
    update_by: Optional[str] = Field(default=None)
