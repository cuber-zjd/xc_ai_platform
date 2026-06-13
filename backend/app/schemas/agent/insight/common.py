from datetime import datetime
from typing import Any

from pydantic import BaseModel


class InsightBaseRead(BaseModel):
    id: int
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class InsightOption(BaseModel):
    label: str
    value: str
    metadata: dict[str, Any] | None = None
