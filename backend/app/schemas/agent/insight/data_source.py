from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead
from app.schemas.agent.insight.crawl import InsightManualUrlCrawlResponse, InsightSearchDiscoveryResponse


class InsightDataSourceFetchConfig(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    max_results: int = Field(default=8, ge=1, le=50)
    crawl_top_n: int = Field(default=8, ge=0, le=50)
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
    create_candidate_from_hits: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class InsightDataSourceCreate(BaseModel):
    source_code: str | None = Field(default=None, max_length=64)
    source_name: str = Field(..., min_length=1, max_length=200)
    source_type: str = Field(..., min_length=1, max_length=50)
    base_url: str | None = Field(default=None, max_length=1000)
    channel_id: int | None = None
    monitor_config_id: int | None = None
    monitor_object_type: str | None = Field(default=None, max_length=30)
    monitor_object_id: int | None = None
    execution_role: str | None = Field(default=None, max_length=50)
    generation_mode: str = Field(default="manual", max_length=30)
    collection_strategy: str = Field(default="standard", max_length=30)
    company_id: int | None = None
    fetch_frequency: str = Field(default="manual", max_length=50)
    fetch_config: InsightDataSourceFetchConfig | dict[str, Any] | None = None
    auth_config_ref: str | None = Field(default=None, max_length=200)
    schedule_enabled: bool | None = None
    visibility_scope: str = Field(default="private", max_length=30)
    status: str = Field(default="enabled", max_length=20)


class InsightDataSourceBatchCreateRequest(BaseModel):
    company_ids: list[int] = Field(..., min_length=1, max_length=500)
    source_types: list[str] = Field(..., min_length=1, max_length=20)
    keyword_template: str | None = Field(default=None, max_length=500)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    fetch_frequency: str = Field(default="daily", max_length=50)
    max_results: int = Field(default=6, ge=1, le=50)
    crawl_top_n: int = Field(default=0, ge=0, le=50)
    freshness: str | None = Field(default="noLimit", max_length=50)
    enable_llm_filter: bool = True
    filter_prompt: str | None = Field(default=None, max_length=2000)
    auto_review_mode: str = Field(default="high_confidence", max_length=30)
    auto_review_min_confidence: float = Field(default=0.72, ge=0, le=1)
    auto_add_to_report_pool: bool = True
    auto_report_folder: str | None = Field(default="期初真实运行素材池", max_length=100)
    visibility_scope: str = Field(default="assigned", max_length=30)
    status: str = Field(default="enabled", max_length=20)
    update_existing: bool = True


class InsightDataSourceBatchCreateItem(BaseModel):
    company_id: int
    company_name: str
    source_type: str
    source_name: str
    source_code: str
    status: str
    data_source_id: int | None = None
    message: str | None = None


class InsightDataSourceBatchCreateResponse(BaseModel):
    requested_company_count: int
    requested_type_count: int
    requested_count: int
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    items: list[InsightDataSourceBatchCreateItem] = Field(default_factory=list)


class InsightDataSourceUpdate(BaseModel):
    source_name: str | None = Field(default=None, min_length=1, max_length=200)
    source_type: str | None = Field(default=None, min_length=1, max_length=50)
    base_url: str | None = Field(default=None, max_length=1000)
    channel_id: int | None = None
    monitor_config_id: int | None = None
    monitor_object_type: str | None = Field(default=None, max_length=30)
    monitor_object_id: int | None = None
    execution_role: str | None = Field(default=None, max_length=50)
    generation_mode: str | None = Field(default=None, max_length=30)
    collection_strategy: str | None = Field(default=None, max_length=30)
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
    channel_id: int | None = None
    channel_name: str | None = None
    monitor_config_id: int | None = None
    monitor_config_name: str | None = None
    monitor_object_type: str | None = None
    monitor_object_id: int | None = None
    execution_role: str | None = None
    generation_mode: str = "manual"
    collection_strategy: str = "standard"
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


class InsightDataSourceGroupRead(BaseModel):
    group_key: str
    monitor_config_id: int | None = None
    monitor_config_name: str | None = None
    monitor_type: str | None = None
    execution_role: str | None = None
    channel_id: int | None = None
    channel_name: str | None = None
    company_id: int | None = None
    company_name: str | None = None
    company_short_name: str | None = None
    sys_company_id: int | None = None
    source_type: str
    source_type_label: str
    total_count: int = 0
    enabled_count: int = 0
    disabled_count: int = 0
    scheduled_count: int = 0
    llm_filter_count: int = 0
    auto_review_count: int = 0
    failed_count: int = 0
    paused_count: int = 0
    latest_success_time: datetime | None = None
    latest_failure_time: datetime | None = None
    next_run_time: datetime | None = None
    visibility_scopes: list[str] = Field(default_factory=list)
    data_source_ids: list[int] = Field(default_factory=list)


class InsightDataSourceExecuteRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=500)
    crawl_top_n: int | None = Field(default=None, ge=0, le=50)


class InsightDataSourceExecuteResponse(BaseModel):
    data_source: InsightDataSourceRead
    manual_result: InsightManualUrlCrawlResponse | None = None
    search_result: InsightSearchDiscoveryResponse | None = None
    search_results: list[InsightSearchDiscoveryResponse] = Field(default_factory=list)
    execution_errors: list[dict[str, Any]] = Field(default_factory=list)
    auto_review_summary: dict[str, Any] | None = None


class InsightDataSourceImportItem(BaseModel):
    row_no: int
    source_name: str
    source_type: str
    base_url: str | None = None
    company_id: int | None = None
    company_name: str | None = None
    keywords: list[str] = Field(default_factory=list)
    project_name: str | None = None
    channel_name: str | None = None
    source_document: str | None = None
    status: str = "created"
    data_source_id: int | None = None
    message: str | None = None


class InsightDataSourceImportResponse(BaseModel):
    file_count: int = 0
    parsed_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    items: list[InsightDataSourceImportItem] = Field(default_factory=list)
    unsupported_channels: list[dict[str, Any]] = Field(default_factory=list)


class InsightDataSourceBulkActionRequest(BaseModel):
    data_source_ids: list[int] = Field(default_factory=list, min_length=1)
    action: str = Field(..., min_length=1, max_length=50)
    status: str | None = Field(default=None, max_length=20)
    fetch_frequency: str | None = Field(default=None, max_length=50)
    schedule_enabled: bool | None = None
    visibility_scope: str | None = Field(default=None, max_length=30)
    fetch_config_patch: dict[str, Any] | None = None
    execute_crawl_top_n: int | None = Field(default=None, ge=0, le=50)


class InsightDataSourceBulkActionResponse(BaseModel):
    action: str
    requested_count: int
    success_count: int = 0
    failed_count: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)


class InsightRequirementSeedRequest(BaseModel):
    file_paths: list[str] = Field(default_factory=list)
    execute: bool = False
    target_intelligence_count: int = Field(default=2000, ge=1, le=10000)
    max_sources_to_execute: int = Field(default=50, ge=1, le=1000)
    crawl_top_n: int = Field(default=8, ge=0, le=50)


class InsightRequirementSeedResponse(BaseModel):
    import_result: InsightDataSourceImportResponse
    execution_result: InsightDataSourceBulkActionResponse | None = None
    target_intelligence_count: int
    current_intelligence_count: int | None = None


class InsightStaleTaskCleanupResponse(BaseModel):
    timeout_minutes: int
    cleaned_count: int
    task_ids: list[int] = Field(default_factory=list)


class InsightDataSourceScheduleExecution(BaseModel):
    data_source_id: int | None = None
    monitor_config_id: int | None = None
    source_name: str
    status: str
    message: str | None = None
    next_run_time: datetime | None = None
    found_count: int = 0
    candidate_count: int = 0
    planned_channel_count: int = 0
    executed_channel_count: int = 0
    skipped_channel_count: int = 0
    paid_channel_call_count: int = 0
    plan_summary: dict[str, Any] | None = None


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
