from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightTaskCreate(BaseModel):
    task_type: str = Field(..., min_length=1, max_length=50)
    data_source_id: int | None = None
    input_payload: dict[str, Any] | None = None


class InsightTaskRead(InsightBaseRead):
    task_uid: str
    task_type: str
    data_source_id: int | None = None
    intelligence_id: int | None = None
    report_id: int | None = None
    status: str
    progress: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_count: int
    input_payload: dict[str, Any] | None = None
    output_payload: dict[str, Any] | None = None
    error_message: str | None = None
