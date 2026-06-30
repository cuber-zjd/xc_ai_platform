from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightMonitorConfig(BaseDBModel, table=True):
    """Insight 面向用户的监测配置。"""

    __tablename__ = "insight_monitor_config"

    config_code: str = Field(index=True, unique=True, max_length=80)
    config_name: str = Field(index=True, max_length=200)
    monitor_type: str = Field(default="topic", index=True, max_length=30)
    object_type: str = Field(default="topic", index=True, max_length=30)
    object_id: int | None = Field(default=None, index=True)
    object_name: str | None = Field(default=None, index=True, max_length=200)
    relation_type: str | None = Field(default=None, index=True, max_length=50)
    enabled_modules: list[str] = Field(default_factory=list, sa_type=JSONB)
    keywords: list[str] = Field(default_factory=list, sa_type=JSONB)
    excluded_keywords: list[str] = Field(default_factory=list, sa_type=JSONB)
    source_channel_ids: list[int] = Field(default_factory=list, sa_type=JSONB)
    monitor_strength: str = Field(default="standard", index=True, max_length=30)
    fetch_frequency: str = Field(default="daily", index=True, max_length=50)
    ai_review_prompt: str | None = Field(default=None)
    ai_review_policy: str = Field(default="ai_auto", index=True, max_length=50)
    owner_user_id: int | None = Field(default=None, index=True)
    owner_dept_id: int | None = Field(default=None, index=True)
    visibility_scope: str = Field(default="assigned", index=True, max_length=30)
    generation_mode: str = Field(default="user_created", index=True, max_length=30)
    config_json: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    last_fetch_time: datetime | None = Field(default=None, index=True)
    last_success_time: datetime | None = Field(default=None, index=True)
    next_run_time: datetime | None = Field(default=None, index=True)
    schedule_enabled: bool = Field(default=True, index=True)
    last_schedule_status: str | None = Field(default=None, max_length=30)
    last_schedule_message: str | None = Field(default=None, max_length=1000)
    consecutive_failure_count: int = Field(default=0)
    last_failure_time: datetime | None = Field(default=None, index=True)
    auto_paused_reason: str | None = Field(default=None, max_length=1000)
    status: str = Field(default="active", index=True, max_length=20)
