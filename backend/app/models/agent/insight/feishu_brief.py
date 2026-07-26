from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightFeishuBriefPlan(BaseDBModel, table=True):
    """由飞书机器人执行的独立简报计划。"""

    __tablename__ = "insight_feishu_brief_plan"

    plan_uid: str = Field(index=True, unique=True, max_length=64)
    plan_name: str = Field(index=True, max_length=160)
    sys_company_id: int | None = Field(default=None, foreign_key="sys_company.id", index=True)
    schedule_frequency: str = Field(default="weekly", index=True, max_length=20)
    weekday: int | None = Field(default=0)
    time_of_day: str = Field(default="09:00", max_length=5)
    timezone: str = Field(default="Asia/Shanghai", max_length=60)
    material_days: int = Field(default=7)
    max_materials: int = Field(default=200)
    prompt_override: str | None = Field(default=None)
    recipients_json: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    next_run_time: datetime | None = Field(default=None, index=True)
    last_run_time: datetime | None = Field(default=None, index=True)
    last_run_id: int | None = Field(default=None, index=True)
    last_status: str | None = Field(default=None, index=True, max_length=30)
    last_error: str | None = Field(default=None, max_length=1000)
    status: str = Field(default="active", index=True, max_length=20)


class InsightFeishuBriefRun(BaseDBModel, table=True):
    """飞书机器人简报的生成、建文档和推送审计。"""

    __tablename__ = "insight_feishu_brief_run"

    run_uid: str = Field(index=True, unique=True, max_length=64)
    plan_id: int = Field(foreign_key="insight_feishu_brief_plan.id", index=True)
    trigger_type: str = Field(default="scheduler", index=True, max_length=30)
    status: str = Field(default="running", index=True, max_length=30)
    period_start: datetime = Field(index=True)
    period_end: datetime = Field(index=True)
    material_count: int = Field(default=0)
    report_title: str | None = Field(default=None, max_length=300)
    document_id: str | None = Field(default=None, index=True, max_length=100)
    document_url: str | None = Field(default=None, max_length=1000)
    pushed_count: int = Field(default=0)
    failed_push_count: int = Field(default=0)
    content_markdown: str | None = Field(default=None)
    output_payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    error_message: str | None = Field(default=None, max_length=2000)
    started_at: datetime | None = Field(default=None, index=True)
    finished_at: datetime | None = Field(default=None, index=True)
