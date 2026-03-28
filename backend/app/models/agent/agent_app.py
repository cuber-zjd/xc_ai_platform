from typing import Optional
from sqlmodel import SQLModel, Field
from app.models.base import BaseDBModel

class AgentAppBase(SQLModel):
    group_id: int = Field(index=True, description="Belonging Group ID (Foreign Key to agent_group.id)")
    name: str = Field(index=True, description="Application/Agent Name")
    description: Optional[str] = Field(default=None, description="Description")
    icon: Optional[str] = Field(default=None, description="Icon name (e.g., lucide icon name) or URL")
    route_path: str = Field(description="Frontend routing path")
    sort_order: Optional[int] = Field(default=0, description="Display Sort Order")
    status: int = Field(default=1, description="Status (1=Normal, 0=Disabled)")

class AgentApp(BaseDBModel, AgentAppBase, table=True):
    __tablename__ = "agent_app"
