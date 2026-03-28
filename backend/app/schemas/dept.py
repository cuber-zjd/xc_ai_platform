from typing import Optional, List
from pydantic import BaseModel

class DeptTreeNode(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    node_type: str = "dept"  # "company" 或 "dept"
    children: List['DeptTreeNode'] = []
