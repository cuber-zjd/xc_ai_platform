from typing import Optional, List
from sqlmodel import SQLModel
from datetime import datetime

# --- Agent Group ---
class AgentGroupBase(SQLModel):
    name: str
    description: Optional[str] = None
    sort_order: int = 0
    status: int = 1

class AgentGroupRead(AgentGroupBase):
    id: int
    create_time: datetime

class AgentGroupCreate(AgentGroupBase):
    pass

class AgentGroupUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[int] = None

# --- Agent App ---
class AgentAppBase(SQLModel):
    group_id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    route_path: str
    sort_order: int = 0
    status: int = 1

class AgentAppRead(AgentAppBase):
    id: int
    create_time: datetime

class AgentAppCreate(AgentAppBase):
    pass

class AgentAppUpdate(SQLModel):
    group_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    route_path: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[int] = None

# --- Permission Assign ---
class RoleAgentAssign(SQLModel):
    role_id: int
    agent_app_ids: List[int]

class DeptAgentAssign(SQLModel):
    dept_id: int
    agent_app_ids: List[int]

# --- Workbench ---
class WorkbenchAgent(SQLModel):
    id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    route_path: str

class WorkbenchGroup(SQLModel):
    id: int
    name: str
    agents: List[WorkbenchAgent]
