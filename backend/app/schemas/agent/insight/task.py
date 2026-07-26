from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightTaskCreate(BaseModel):
    task_type: str = Field(..., min_length=1, max_length=50)
    data_source_id: int | None = None
    monitor_config_id: int | None = None
    source_channel_id: int | None = None
    input_payload: dict[str, Any] | None = None


class InsightTaskRead(InsightBaseRead):
    task_uid: str
    task_type: str
    data_source_id: int | None = None
    monitor_config_id: int | None = None
    source_channel_id: int | None = None
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


class InsightSchedulerRunLogRead(BaseModel):
    id: int
    task_uid: str
    status: str
    triggered_by: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float = 0
    discovery_checked_count: int = 0
    discovery_hit_count: int = 0
    discovery_candidate_count: int = 0
    discovery_failed_count: int = 0
    checked_count: int = 0
    due_count: int = 0
    executed_count: int = 0
    failed_count: int = 0
    report_executed_count: int = 0
    report_failed_count: int = 0
    feishu_created_count: int = 0
    feishu_updated_count: int = 0
    feishu_failed_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model_call_count: int = 0
    token_models: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
