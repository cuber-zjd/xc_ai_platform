from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class InsightFeishuBriefRecipient(BaseModel):
    receive_id_type: Literal["open_id", "user_id", "union_id", "email", "chat_id"] = "open_id"
    receive_id: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=100)


class InsightFeishuBriefPlanCreate(BaseModel):
    plan_name: str = Field(min_length=1, max_length=160)
    sys_company_id: int | None = None
    schedule_frequency: Literal["daily", "weekly"] = "weekly"
    weekday: int | None = Field(default=0, ge=0, le=6)
    time_of_day: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    material_days: int = Field(default=7, ge=1, le=90)
    max_materials: int = Field(default=200, ge=20, le=500)
    prompt_override: str | None = None
    recipients: list[InsightFeishuBriefRecipient] = Field(default_factory=list)
    status: Literal["active", "paused"] = "active"

    @model_validator(mode="after")
    def validate_schedule(self) -> "InsightFeishuBriefPlanCreate":
        hour, minute = [int(item) for item in self.time_of_day.split(":", 1)]
        if hour > 23 or minute > 59:
            raise ValueError("执行时间格式必须为 HH:mm")
        return self


class InsightFeishuBriefPlanUpdate(BaseModel):
    plan_name: str | None = Field(default=None, min_length=1, max_length=160)
    sys_company_id: int | None = None
    schedule_frequency: Literal["daily", "weekly"] | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    time_of_day: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    material_days: int | None = Field(default=None, ge=1, le=90)
    max_materials: int | None = Field(default=None, ge=20, le=500)
    prompt_override: str | None = None
    recipients: list[InsightFeishuBriefRecipient] | None = None
    status: Literal["active", "paused"] | None = None


class InsightFeishuBriefPlanRead(BaseModel):
    id: int
    plan_uid: str
    plan_name: str
    sys_company_id: int | None
    sys_company_name: str | None
    schedule_frequency: str
    weekday: int | None
    time_of_day: str
    timezone: str
    material_days: int
    max_materials: int
    prompt_override: str | None
    recipients: list[InsightFeishuBriefRecipient]
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
    status: str
    period_start: datetime
    period_end: datetime
    material_count: int
    report_title: str | None
    document_id: str | None
    document_url: str | None
    pushed_count: int
    failed_push_count: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    create_time: datetime


class InsightFeishuBriefRunResponse(BaseModel):
    run: InsightFeishuBriefRunRead
    message: str


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
