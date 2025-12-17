from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

class BaseDBModel(SQLModel):
    """
    Common fields for all database models.
    """
    id: int | None = Field(default=None, primary_key=True)
    create_time: datetime = Field(default_factory=datetime.now)
    update_time: datetime = Field(default_factory=datetime.now)
    create_by: Optional[str] = Field(default=None)
    update_by: Optional[str] = Field(default=None)
    comment: Optional[str] = Field(default=None, description="Remarks")
    is_deleted: int = Field(default=0, description="0=Active, 1=Deleted") # Standard soft delete
