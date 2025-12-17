from typing import Optional
from sqlmodel import SQLModel, Field
from app.models.base import BaseDBModel

class SysCompanyBase(SQLModel):
    sync_id: Optional[str] = Field(default=None, index=True, description="Original ID (companyid)")
    name: str = Field(index=True, description="Company Name (companyname)")
    code: Optional[str] = Field(default=None, description="Company Code (companycode)")
    parent_id: Optional[str] = Field(default=None, description="Parent Company ID (parentid)")
    order: Optional[int] = Field(default=0, description="Display Order (orderindex)")

class SysCompany(BaseDBModel, SysCompanyBase, table=True):
    __tablename__ = "sys_company"
