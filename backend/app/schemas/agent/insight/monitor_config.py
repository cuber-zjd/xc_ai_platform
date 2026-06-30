from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightMonitorConfigCreate(BaseModel):
    config_code: str | None = Field(default=None, max_length=80)
    config_name: str = Field(..., min_length=1, max_length=200)
    monitor_type: str = Field(default="topic", max_length=30)
    object_type: str = Field(default="topic", max_length=30)
    object_id: int | None = None
    object_name: str | None = Field(default=None, max_length=200)
    relation_type: str | None = Field(default=None, max_length=50)
    enabled_modules: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    source_channel_ids: list[int] = Field(default_factory=list)
    monitor_strength: str = Field(default="standard", max_length=30)
    fetch_frequency: str = Field(default="daily", max_length=50)
    ai_review_prompt: str | None = Field(default=None, max_length=4000)
    ai_review_policy: str = Field(default="ai_auto", max_length=50)
    visibility_scope: str = Field(default="assigned", max_length=30)
    generation_mode: str = Field(default="user_created", max_length=30)
    config_json: dict[str, Any] | None = None
    status: str = Field(default="active", max_length=20)


class InsightMonitorConfigUpdate(BaseModel):
    config_name: str | None = Field(default=None, min_length=1, max_length=200)
    monitor_type: str | None = Field(default=None, max_length=30)
    object_type: str | None = Field(default=None, max_length=30)
    object_id: int | None = None
    object_name: str | None = Field(default=None, max_length=200)
    relation_type: str | None = Field(default=None, max_length=50)
    enabled_modules: list[str] | None = None
    keywords: list[str] | None = None
    excluded_keywords: list[str] | None = None
    source_channel_ids: list[int] | None = None
    monitor_strength: str | None = Field(default=None, max_length=30)
    fetch_frequency: str | None = Field(default=None, max_length=50)
    ai_review_prompt: str | None = Field(default=None, max_length=4000)
    ai_review_policy: str | None = Field(default=None, max_length=50)
    visibility_scope: str | None = Field(default=None, max_length=30)
    generation_mode: str | None = Field(default=None, max_length=30)
    config_json: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=20)


class InsightMonitorConfigRead(InsightBaseRead):
    config_code: str
    config_name: str
    monitor_type: str
    object_type: str
    object_id: int | None = None
    object_name: str | None = None
    relation_type: str | None = None
    enabled_modules: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    source_channel_ids: list[int] = Field(default_factory=list)
    monitor_strength: str
    fetch_frequency: str
    ai_review_prompt: str | None = None
    ai_review_policy: str
    owner_user_id: int | None = None
    owner_dept_id: int | None = None
    visibility_scope: str
    generation_mode: str
    config_json: dict[str, Any] | None = None
    last_fetch_time: datetime | None = None
    last_success_time: datetime | None = None
    next_run_time: datetime | None = None
    schedule_enabled: bool = True
    last_schedule_status: str | None = None
    last_schedule_message: str | None = None
    consecutive_failure_count: int = 0
    last_failure_time: datetime | None = None
    auto_paused_reason: str | None = None
    status: str
    execution_source_count: int = 0


class InsightMonitorConfigListParams(BaseModel):
    page: int = 1
    size: int = 20
    keyword: str | None = None
    monitor_type: str | None = None
    status: str | None = None


class InsightLegacySourceSyncResponse(BaseModel):
    checked_count: int = 0
    created_config_count: int = 0
    linked_source_count: int = 0
    linked_channel_count: int = 0
    updated_role_count: int = 0
    skipped_count: int = 0


class InsightLegacySourceRetireResponse(BaseModel):
    checked_count: int = 0
    retired_count: int = 0
    hydrated_config_count: int = 0
    skipped_count: int = 0
