from typing import Optional
from sqlmodel import SQLModel, Field
from app.models.base import BaseDBModel

class AgentGroupBase(SQLModel):
    name: str = Field(index=True, unique=True, description="Group Name")
    description: Optional[str] = Field(default=None, description="Group Description")
    sort_order: Optional[int] = Field(default=0, description="Display Sort Order")
    status: int = Field(default=1, description="Status (1=Normal, 0=Disabled)")

class AgentGroup(BaseDBModel, AgentGroupBase, table=True):
    __tablename__ = "agent_group"
