from typing import Optional, List
from sqlmodel import SQLModel
from datetime import datetime

class SysRoleBase(SQLModel):
    name: str
    code: str
    status: int = 1
    order: int = 0

class RoleRead(SysRoleBase):
    id: int
    create_time: datetime
    update_time: datetime

class RoleCreate(SysRoleBase):
    pass

class RoleUpdate(SQLModel):
    name: Optional[str] = None
    code: Optional[str] = None
    status: Optional[int] = None
    order: Optional[int] = None

class UserRoleAssign(SQLModel):
    user_id: int
    role_ids: List[int]
