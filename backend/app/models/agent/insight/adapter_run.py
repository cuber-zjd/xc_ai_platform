from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightChannelAdapterRun(BaseDBModel, table=True):
    """渠道适配器运行审计，记录成功、失败、快照和重试信息。"""

    __tablename__ = "insight_channel_adapter_run"

    channel_id: int | None = Field(default=None, foreign_key="insight_channel.id", index=True)
    channel_code: str = Field(index=True, max_length=80)
    monitor_config_id: int | None = Field(default=None, foreign_key="insight_monitor_config.id", index=True)
    keyword: str = Field(index=True, max_length=300)
    run_type: str = Field(default="manual_test", index=True, max_length=30)
    status: str = Field(default="running", index=True, max_length=30)
    started_at: datetime = Field(default_factory=datetime.now, index=True)
    finished_at: datetime | None = Field(default=None, index=True)
    duration_ms: int = Field(default=0)
    hit_count: int = Field(default=0)
    kept_count: int = Field(default=0)
    dedupe_count: int = Field(default=0)
    candidate_count: int = Field(default=0)
    formal_count: int = Field(default=0)
    vectorized_count: int = Field(default=0)
    retry_count: int = Field(default=0)
    error_type: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=2000)
    page_url: str | None = Field(default=None, max_length=1200)
    request_payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    response_excerpt: str | None = Field(default=None)
    snapshot_html_path: str | None = Field(default=None, max_length=1000)
    screenshot_path: str | None = Field(default=None, max_length=1000)
    raw_output_path: str | None = Field(default=None, max_length=1000)
    adapter_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
