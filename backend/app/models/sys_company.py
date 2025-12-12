from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

class SysCompanyBase(SQLModel):
    sync_id: Optional[str] = Field(default=None, index=True, description="Original ID (companyid)")
    name: str = Field(index=True, description="Company Name (companyname)")
    code: Optional[str] = Field(default=None, description="Company Code (companycode)")
    parent_id: Optional[str] = Field(default=None, description="Parent Company ID (parentid)")
    order: Optional[int] = Field(default=0, description="Display Order (orderindex)")
    
    status: int = Field(default=1, description="Status: 1=Normal, 0=Deleted")
    comment: Optional[str] = Field(default=None, description="Remarks")

class SysCompany(SysCompanyBase, table=True):
    __tablename__ = "sys_company"
    
    id: int | None = Field(default=None, primary_key=True)
    create_time: datetime = Field(default_factory=datetime.now)
    update_time: datetime = Field(default_factory=datetime.now)
    create_by: Optional[str] = Field(default=None)
    update_by: Optional[str] = Field(default=None)
