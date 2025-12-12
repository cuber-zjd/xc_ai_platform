from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

class SysPostBase(SQLModel):
    sync_id: Optional[str] = Field(default=None, index=True, description="Original ID (postno)")
    name: str = Field(index=True, description="Post Name (postname)")
    code: Optional[str] = Field(default=None, description="Post Code (postno)")
    dept_id: Optional[str] = Field(default=None, index=True, description="Belonging Dept ID (dept_id)")
    
    status: int = Field(default=1, description="Status: 1=Normal, 0=Deleted")
    comment: Optional[str] = Field(default=None, description="Remarks")

class SysPost(SysPostBase, table=True):
    __tablename__ = "sys_post"
    
    id: int | None = Field(default=None, primary_key=True)
    create_time: datetime = Field(default_factory=datetime.now)
    update_time: datetime = Field(default_factory=datetime.now)
    create_by: Optional[str] = Field(default=None)
    update_by: Optional[str] = Field(default=None)
