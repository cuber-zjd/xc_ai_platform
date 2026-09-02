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
    owner_user_id: int | None = Field(default=None, foreign_key="sys_user.id", index=True)
    sys_company_id: int | None = Field(default=None, foreign_key="sys_company.id", index=True)
    schedule_frequency: str = Field(default="weekly", index=True, max_length=20)
    weekday: int | None = Field(default=0)
    day_of_month: int | None = Field(default=1)
    time_of_day: str = Field(default="09:00", max_length=5)
    review_weekday: int | None = Field(default=0)
    review_time: str = Field(default="10:30", max_length=5)
    release_weekday: int | None = Field(default=1)
    release_time: str = Field(default="15:00", max_length=5)
    timezone: str = Field(default="Asia/Shanghai", max_length=60)
    material_days: int = Field(default=7)
    max_materials: int = Field(default=200)
    generation_strategy: str = Field(default="auto", index=True, max_length=40)
    prompt_override: str | None = Field(default=None)
    generation_rules_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    workflow_config_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    prompt_config_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    material_scope_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    template_markdown: str | None = Field(default=None)
    config_version: int = Field(default=1)
    # recipients_json 保留为上午审阅组，兼容已有计划数据。
    recipients_json: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    afternoon_recipients_json: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    afternoon_push_time: str = Field(default="15:00", max_length=5)
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
    run_mode: str = Field(default="formal", index=True, max_length=20)
    status: str = Field(default="running", index=True, max_length=30)
    period_start: datetime = Field(index=True)
    period_end: datetime = Field(index=True)
    material_count: int = Field(default=0)
    report_title: str | None = Field(default=None, max_length=300)
    document_id: str | None = Field(default=None, index=True, max_length=100)
    document_url: str | None = Field(default=None, max_length=1000)
    pushed_count: int = Field(default=0)
    failed_push_count: int = Field(default=0)
    afternoon_push_scheduled_at: datetime | None = Field(default=None, index=True)
    afternoon_push_status: str | None = Field(default=None, index=True, max_length=30)
    afternoon_pushed_count: int = Field(default=0)
    afternoon_failed_push_count: int = Field(default=0)
    review_push_scheduled_at: datetime | None = Field(default=None, index=True)
    review_push_status: str | None = Field(default=None, index=True, max_length=30)
    review_pushed_count: int = Field(default=0)
    review_failed_push_count: int = Field(default=0)
    occurrence_id: int | None = Field(default=None, index=True)
    config_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    owner_transfer_status: str | None = Field(default=None, max_length=30)
    content_markdown: str | None = Field(default=None)
    output_payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    error_message: str | None = Field(default=None, max_length=2000)
    started_at: datetime | None = Field(default=None, index=True)
    finished_at: datetime | None = Field(default=None, index=True)


class InsightFeishuBriefOccurrence(BaseDBModel, table=True):
    """周报单期调度实例；可覆盖某一期而不改变后续常规计划。"""

    __tablename__ = "insight_feishu_brief_occurrence"

    occurrence_uid: str = Field(index=True, unique=True, max_length=64)
    plan_id: int = Field(foreign_key="insight_feishu_brief_plan.id", index=True)
    period_key: str = Field(index=True, max_length=30)
    generation_scheduled_at: datetime = Field(index=True)
    review_scheduled_at: datetime = Field(index=True)
    release_scheduled_at: datetime = Field(index=True)
    material_scope_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    recipients_json: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    release_recipients_json: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    config_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    status: str = Field(default="pending", index=True, max_length=30)
    run_id: int | None = Field(default=None, index=True)
    error_message: str | None = Field(default=None, max_length=2000)


class InsightFeishuBriefPlanVersion(BaseDBModel, table=True):
    """飞书简报计划配置版本。"""

    __tablename__ = "insight_feishu_brief_plan_version"

    plan_id: int = Field(foreign_key="insight_feishu_brief_plan.id", index=True)
    version_no: int = Field(index=True)
    config_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    diff_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    changed_by_user_id: int | None = Field(default=None, foreign_key="sys_user.id", index=True)


class InsightFeishuBriefAgentStage(BaseDBModel, table=True):
    """周报多智能体每一阶段的执行审计。"""

    __tablename__ = "insight_feishu_brief_agent_stage"

    run_id: int = Field(foreign_key="insight_feishu_brief_run.id", index=True)
    stage_code: str = Field(index=True, max_length=60)
    stage_name: str = Field(max_length=100)
    sequence_no: int = Field(default=0)
    status: str = Field(default="running", index=True, max_length=30)
    input_summary: str | None = Field(default=None)
    output_content: str | None = Field(default=None)
    output_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    model_name: str | None = Field(default=None, max_length=120)
    token_usage_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    duration_ms: int = Field(default=0)
    error_message: str | None = Field(default=None, max_length=2000)
    started_at: datetime | None = Field(default=None, index=True)
    finished_at: datetime | None = Field(default=None, index=True)
