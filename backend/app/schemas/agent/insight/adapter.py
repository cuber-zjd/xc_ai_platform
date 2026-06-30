from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightChannelAdapterDefinitionRead(BaseModel):
    channel_code: str
    source_name: str
    task_dir: str
    script_name: str | None = None
    function_name: str | None = None
    status: str
    adapter_kind: str
    cooldown_seconds: float
    priority: str
    note: str | None = None


class InsightChannelAdapterRunRead(InsightBaseRead):
    channel_id: int | None = None
    channel_code: str
    monitor_config_id: int | None = None
    keyword: str
    run_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int
    hit_count: int
    kept_count: int
    dedupe_count: int
    candidate_count: int
    formal_count: int
    vectorized_count: int
    retry_count: int
    error_type: str | None = None
    error_message: str | None = None
    page_url: str | None = None
    request_payload: dict[str, Any] | None = None
    response_excerpt: str | None = None
    snapshot_html_path: str | None = None
    screenshot_path: str | None = None
    raw_output_path: str | None = None
    adapter_metadata: dict[str, Any] | None = None


class InsightChannelAdapterRunListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    channel_code: str | None = None
    status: str | None = None
    run_type: str | None = None
