from typing import Optional
from sqlmodel import SQLModel, Field
from app.models.base import BaseDBModel

class SysRoleBase(SQLModel):
    name: str = Field(index=True, description="Role Name")
    code: str = Field(index=True, unique=True, description="Role Code")
    status: int = Field(default=1, description="Status (1=Normal, 0=Disabled)")
    order: Optional[int] = Field(default=0, description="Display Order")

class SysRole(BaseDBModel, SysRoleBase, table=True):
    __tablename__ = "sys_role"

class SysUserRole(BaseDBModel, table=True):
    __tablename__ = "sys_user_role"
    user_id: int = Field(index=True, description="User ID (Foreign Key to sys_user.id)")
    role_id: int = Field(index=True, description="Role ID (Foreign Key to sys_role.id)")
