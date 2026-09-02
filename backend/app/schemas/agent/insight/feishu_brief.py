from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class InsightFeishuBriefRecipient(BaseModel):
    receive_id_type: Literal["open_id", "user_id", "union_id", "email", "chat_id"] = "open_id"
    receive_id: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=100)


class InsightFeishuBriefGenerationRules(BaseModel):
    focus_topics: list[str] = Field(default_factory=list, max_length=30)
    value_departments: list[str] = Field(
        default_factory=lambda: ["销售", "市场", "研发", "采购", "供应链", "经营管理"],
        max_length=10,
    )
    excluded_content: list[str] = Field(
        default_factory=lambda: ["广告软文", "榜单", "招聘", "通用专利", "旧闻", "重复事件"],
        max_length=20,
    )
    primary_score: int = Field(default=78, ge=60, le=100)
    supporting_score: int = Field(default=68, ge=50, le=99)
    section_priorities: dict[str, int] = Field(
        default_factory=lambda: {"政策": 3, "竞对": 3, "客户": 5, "技术": 3, "原料": 4},
    )
    minimum_citations: int = Field(default=7, ge=5, le=30)
    maximum_citations: int = Field(default=25, ge=7, le=40)
    writing_depth: Literal["concise", "balanced", "detailed"] = "balanced"
    include_business_insight: bool = True

    @model_validator(mode="after")
    def validate_rules(self) -> "InsightFeishuBriefGenerationRules":
        if self.supporting_score >= self.primary_score:
            raise ValueError("补充素材评分必须低于主线素材评分")
        if self.minimum_citations > self.maximum_citations:
            raise ValueError("最少引用数不能高于最多引用数")
        allowed_sections = {"政策", "竞对", "客户", "技术", "原料"}
        self.section_priorities = {
            key: min(max(int(value), 0), 5)
            for key, value in self.section_priorities.items()
            if key in allowed_sections
        }
        for key in allowed_sections:
            self.section_priorities.setdefault(key, 3)
        return self


class InsightFeishuBriefWorkflowConfig(BaseModel):
    max_revision_rounds: int = Field(default=2, ge=1, le=4)
    research_sections: list[Literal["政策", "竞对", "客户", "技术", "原料"]] = Field(
        default_factory=lambda: ["政策", "竞对", "客户", "技术", "原料"]
    )


class InsightFeishuBriefPromptConfig(BaseModel):
    planning: str = Field(default="", max_length=12000)
    research: str = Field(default="", max_length=12000)
    writing: str = Field(default="", max_length=20000)
    reviewing: str = Field(default="", max_length=12000)
    revision: str = Field(default="", max_length=12000)


class InsightFeishuBriefMaterialScope(BaseModel):
    mode: Literal["rolling_days", "fixed_weekdays", "custom_range"] = "rolling_days"
    rolling_days: int = Field(default=7, ge=1, le=90)
    start_weekday: int = Field(default=0, ge=0, le=6)
    end_weekday: int = Field(default=6, ge=0, le=6)
    custom_start: datetime | None = None
    custom_end: datetime | None = None
    filters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_custom_range(self) -> "InsightFeishuBriefMaterialScope":
        if self.mode == "custom_range":
            if not self.custom_start or not self.custom_end:
                raise ValueError("自定义素材范围必须填写开始和结束时间")
            if self.custom_start >= self.custom_end:
                raise ValueError("素材开始时间必须早于结束时间")
        return self


class InsightFeishuBriefPlanCreate(BaseModel):
    plan_name: str = Field(min_length=1, max_length=160)
    sys_company_id: int | None = None
    schedule_frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    weekday: int | None = Field(default=0, ge=0, le=6)
    day_of_month: int | None = Field(default=1, ge=1, le=31)
    time_of_day: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    review_weekday: int | None = Field(default=0, ge=0, le=6)
    review_time: str = Field(default="10:30", pattern=r"^\d{2}:\d{2}$")
    release_weekday: int | None = Field(default=1, ge=0, le=6)
    release_time: str = Field(default="15:00", pattern=r"^\d{2}:\d{2}$")
    material_days: int = Field(default=7, ge=1, le=90)
    max_materials: int = Field(default=200, ge=20, le=500)
    generation_strategy: Literal[
        "auto",
        "single_model",
        "section_parallel",
        "multi_agent_ensemble",
    ] = "auto"
    prompt_override: str | None = None
    generation_rules: InsightFeishuBriefGenerationRules = Field(
        default_factory=InsightFeishuBriefGenerationRules
    )
    workflow_config: InsightFeishuBriefWorkflowConfig = Field(
        default_factory=InsightFeishuBriefWorkflowConfig
    )
    prompt_config: InsightFeishuBriefPromptConfig = Field(
        default_factory=InsightFeishuBriefPromptConfig
    )
    material_scope: InsightFeishuBriefMaterialScope = Field(
        default_factory=InsightFeishuBriefMaterialScope
    )
    template_markdown: str | None = None
    recipients: list[InsightFeishuBriefRecipient] = Field(default_factory=list)
    afternoon_recipients: list[InsightFeishuBriefRecipient] = Field(default_factory=list)
    afternoon_push_time: str = Field(default="15:00", pattern=r"^\d{2}:\d{2}$")
    status: Literal["active", "paused"] = "active"

    @model_validator(mode="after")
    def validate_schedule(self) -> "InsightFeishuBriefPlanCreate":
        for label, value in (
            ("执行时间", self.time_of_day),
            ("审阅时间", self.review_time),
            ("正式推送时间", self.release_time),
            ("兼容下午推送时间", self.afternoon_push_time),
        ):
            hour, minute = [int(item) for item in value.split(":", 1)]
            if hour > 23 or minute > 59:
                raise ValueError(f"{label}格式必须为 HH:mm")
        return self


class InsightFeishuBriefPlanUpdate(BaseModel):
    plan_name: str | None = Field(default=None, min_length=1, max_length=160)
    sys_company_id: int | None = None
    schedule_frequency: Literal["daily", "weekly", "monthly"] | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    time_of_day: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    review_weekday: int | None = Field(default=None, ge=0, le=6)
    review_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    release_weekday: int | None = Field(default=None, ge=0, le=6)
    release_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    material_days: int | None = Field(default=None, ge=1, le=90)
    max_materials: int | None = Field(default=None, ge=20, le=500)
    generation_strategy: Literal[
        "auto",
        "single_model",
        "section_parallel",
        "multi_agent_ensemble",
    ] | None = None
    prompt_override: str | None = None
    generation_rules: InsightFeishuBriefGenerationRules | None = None
    workflow_config: InsightFeishuBriefWorkflowConfig | None = None
    prompt_config: InsightFeishuBriefPromptConfig | None = None
    material_scope: InsightFeishuBriefMaterialScope | None = None
    template_markdown: str | None = None
    recipients: list[InsightFeishuBriefRecipient] | None = None
    afternoon_recipients: list[InsightFeishuBriefRecipient] | None = None
    afternoon_push_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    status: Literal["active", "paused"] | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> "InsightFeishuBriefPlanUpdate":
        for label, value in (
            ("执行时间", self.time_of_day),
            ("审阅时间", self.review_time),
            ("正式推送时间", self.release_time),
            ("兼容下午推送时间", self.afternoon_push_time),
        ):
            if not value:
                continue
            hour, minute = [int(item) for item in value.split(":", 1)]
            if hour > 23 or minute > 59:
                raise ValueError(f"{label}格式必须为 HH:mm")
        return self


class InsightFeishuBriefPlanRead(BaseModel):
    id: int
    plan_uid: str
    plan_name: str
    owner_user_id: int | None
    can_edit: bool = False
    sys_company_id: int | None
    sys_company_name: str | None
    schedule_frequency: str
    weekday: int | None
    day_of_month: int | None
    time_of_day: str
    review_weekday: int | None
    review_time: str
    release_weekday: int | None
    release_time: str
    timezone: str
    material_days: int
    max_materials: int
    generation_strategy: str
    prompt_override: str | None
    generation_rules: InsightFeishuBriefGenerationRules
    workflow_config: InsightFeishuBriefWorkflowConfig
    prompt_config: InsightFeishuBriefPromptConfig
    material_scope: InsightFeishuBriefMaterialScope
    template_markdown: str
    config_version: int
    recipients: list[InsightFeishuBriefRecipient]
    afternoon_recipients: list[InsightFeishuBriefRecipient]
    afternoon_push_time: str
    next_run_time: datetime | None
    last_run_time: datetime | None
    last_run_id: int | None
    last_status: str | None
    last_error: str | None
    status: str
    create_time: datetime
    update_time: datetime


class InsightFeishuBriefRunRead(BaseModel):
    id: int
    plan_id: int
    trigger_type: str
    run_mode: str
    status: str
    period_start: datetime
    period_end: datetime
    material_count: int
    report_title: str | None
    document_id: str | None
    document_url: str | None
    pushed_count: int
    failed_push_count: int
    afternoon_push_scheduled_at: datetime | None
    afternoon_push_status: str | None
    afternoon_pushed_count: int
    afternoon_failed_push_count: int
    review_push_scheduled_at: datetime | None
    review_push_status: str | None
    review_pushed_count: int
    review_failed_push_count: int
    occurrence_id: int | None
    owner_transfer_status: str | None
    error_message: str | None
    output_payload: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None
    finished_at: datetime | None
    create_time: datetime


class InsightFeishuBriefRunResponse(BaseModel):
    run: InsightFeishuBriefRunRead
    message: str


class InsightFeishuBriefRunRequest(BaseModel):
    period_start: datetime | None = None
    period_end: datetime | None = None
    publish_candidate_documents: bool = True
    push_final: bool = True

    @model_validator(mode="after")
    def validate_period(self) -> "InsightFeishuBriefRunRequest":
        if self.period_start and self.period_end and self.period_start >= self.period_end:
            raise ValueError("素材开始时间必须早于结束时间")
        return self


class InsightFeishuBriefOccurrenceOverride(BaseModel):
    period_key: str = Field(default="", max_length=30)
    generation_scheduled_at: datetime
    review_scheduled_at: datetime
    release_scheduled_at: datetime
    material_scope: InsightFeishuBriefMaterialScope | None = None
    recipients: list[InsightFeishuBriefRecipient] | None = None
    release_recipients: list[InsightFeishuBriefRecipient] | None = None

    @model_validator(mode="after")
    def validate_times(self) -> "InsightFeishuBriefOccurrenceOverride":
        if self.review_scheduled_at > self.release_scheduled_at:
            raise ValueError("审阅推送时间不能晚于正式推送时间")
        return self


class InsightFeishuBriefOccurrenceRead(BaseModel):
    id: int
    plan_id: int
    period_key: str
    generation_scheduled_at: datetime
    review_scheduled_at: datetime
    release_scheduled_at: datetime
    material_scope: InsightFeishuBriefMaterialScope
    status: str
    run_id: int | None
    error_message: str | None


class InsightFeishuBriefDebugRequest(BaseModel):
    draft_config: InsightFeishuBriefPlanCreate
    period_start: datetime | None = None
    period_end: datetime | None = None


class InsightFeishuBriefAgentStageRead(BaseModel):
    id: int
    run_id: int
    stage_code: str
    stage_name: str
    sequence_no: int
    status: str
    output_content: str | None
    output_json: dict[str, Any]
    model_name: str | None
    token_usage_json: dict[str, Any]
    duration_ms: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class InsightFeishuBriefPlanVersionRead(BaseModel):
    id: int
    plan_id: int
    version_no: int
    config_json: dict[str, Any]
    diff_json: dict[str, Any]
    changed_by_user_id: int | None
    create_time: datetime


class InsightFeishuBriefOptionsRead(BaseModel):
    enabled: bool
    configured: bool
    bot_name: str
    folder_configured: bool
    app_configured: bool
    default_recipient_count: int
    warnings: list[str] = Field(default_factory=list)
    fixed_format: list[str] = Field(default_factory=list)
    prompt_template: str


class InsightFeishuBriefDueRunResponse(BaseModel):
    checked_count: int
    due_count: int
    success_count: int
    failed_count: int
    results: list[dict[str, Any]] = Field(default_factory=list)
