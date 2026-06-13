from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead
from app.schemas.agent.insight.crawl import InsightManualUrlCrawlResponse, InsightSearchDiscoveryResponse


class InsightDataSourceFetchConfig(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    max_results: int = Field(default=8, ge=1, le=20)
    crawl_top_n: int = Field(default=8, ge=0, le=20)
    freshness: str | None = Field(default="noLimit", max_length=50)
    schedule_type: str = Field(default="manual", max_length=30)
    cron_expression: str | None = Field(default=None, max_length=100)
    enable_llm_filter: bool = False
    filter_prompt: str | None = Field(default=None, max_length=2000)
    llm_min_score: float | None = Field(default=None, ge=0, le=1)
    llm_failure_policy: str = Field(default="keep", max_length=30)
    auto_review_mode: str = Field(default="off", max_length=30)
    auto_review_min_confidence: float = Field(default=0.75, ge=0, le=1)
    auto_review_required_tags: list[str] = Field(default_factory=list)
    auto_review_intelligence_types: list[str] = Field(default_factory=list)
    auto_add_to_report_pool: bool = False
    auto_report_folder: str | None = Field(default=None, max_length=100)
    extra: dict[str, Any] = Field(default_factory=dict)


class InsightDataSourceCreate(BaseModel):
    source_code: str | None = Field(default=None, max_length=64)
    source_name: str = Field(..., min_length=1, max_length=200)
    source_type: str = Field(..., min_length=1, max_length=50)
    base_url: str | None = Field(default=None, max_length=1000)
    company_id: int | None = None
    fetch_frequency: str = Field(default="manual", max_length=50)
    fetch_config: InsightDataSourceFetchConfig | dict[str, Any] | None = None
    auth_config_ref: str | None = Field(default=None, max_length=200)
    schedule_enabled: bool | None = None
    visibility_scope: str = Field(default="private", max_length=30)
    status: str = Field(default="enabled", max_length=20)


class InsightDataSourceUpdate(BaseModel):
    source_name: str | None = Field(default=None, min_length=1, max_length=200)
    source_type: str | None = Field(default=None, min_length=1, max_length=50)
    base_url: str | None = Field(default=None, max_length=1000)
    company_id: int | None = None
    fetch_frequency: str | None = Field(default=None, max_length=50)
    fetch_config: InsightDataSourceFetchConfig | dict[str, Any] | None = None
    auth_config_ref: str | None = Field(default=None, max_length=200)
    schedule_enabled: bool | None = None
    visibility_scope: str | None = Field(default=None, max_length=30)
    status: str | None = Field(default=None, max_length=20)


class InsightDataSourceRead(InsightBaseRead):
    source_code: str
    source_name: str
    source_type: str
    base_url: str | None = None
    company_id: int | None = None
    company_name: str | None = None
    company_short_name: str | None = None
    fetch_frequency: str
    fetch_config: dict[str, Any] | None = None
    auth_config_ref: str | None = None
    last_fetch_time: datetime | None = None
    last_success_time: datetime | None = None
    next_run_time: datetime | None = None
    schedule_enabled: bool = False
    last_schedule_status: str | None = None
    last_schedule_message: str | None = None
    consecutive_failure_count: int = 0
    last_failure_time: datetime | None = None
    auto_paused_reason: str | None = None
    owner_user_id: int | None = None
    owner_dept_id: int | None = None
    visibility_scope: str = "private"
    status: str


class InsightDataSourceExecuteRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=500)
    crawl_top_n: int | None = Field(default=None, ge=0, le=20)


class InsightDataSourceExecuteResponse(BaseModel):
    data_source: InsightDataSourceRead
    manual_result: InsightManualUrlCrawlResponse | None = None
    search_result: InsightSearchDiscoveryResponse | None = None
    search_results: list[InsightSearchDiscoveryResponse] = Field(default_factory=list)
    execution_errors: list[dict[str, Any]] = Field(default_factory=list)
    auto_review_summary: dict[str, Any] | None = None


class InsightStaleTaskCleanupResponse(BaseModel):
    timeout_minutes: int
    cleaned_count: int
    task_ids: list[int] = Field(default_factory=list)


class InsightDataSourceScheduleExecution(BaseModel):
    data_source_id: int
    source_name: str
    status: str
    message: str | None = None
    next_run_time: datetime | None = None
    found_count: int = 0
    candidate_count: int = 0


class InsightDataSourceScheduleRunResponse(BaseModel):
    checked_count: int
    due_count: int
    executed_count: int
    failed_count: int
    executions: list[InsightDataSourceScheduleExecution] = Field(default_factory=list)


class InsightSchedulerStatusRead(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: int
    batch_limit: int
    startup_delay_seconds: int
    advisory_lock_id: int
    scheduler_user_id: int
    failure_pause_threshold: int
    config_health: str
    config_warnings: list[str] = Field(default_factory=list)
    config_recommendations: list[str] = Field(default_factory=list)
    last_tick_at: datetime | None = None
    last_success_at: datetime | None = None
    next_tick_at: datetime | None = None
    last_error: str | None = None
    last_result: dict[str, Any] | None = None
