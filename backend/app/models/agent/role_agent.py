from sqlmodel import Field
from app.models.base import BaseDBModel

class SysRoleAgent(BaseDBModel, table=True):
    __tablename__ = "sys_role_agent"
    role_id: int = Field(index=True, description="Role ID (Foreign Key to sys_role.id)")
    agent_app_id: int = Field(index=True, description="Agent App ID (Foreign Key to agent_app.id)")
