from sqlmodel import Field
from app.models.base import BaseDBModel

class SysDeptAgent(BaseDBModel, table=True):
    __tablename__ = "sys_dept_agent"
    dept_id: int = Field(index=True, description="Dept ID (Foreign Key to sys_dept.id)")
    agent_app_id: int = Field(index=True, description="Agent App ID (Foreign Key to agent_app.id)")
