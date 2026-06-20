from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightReportSubscription(BaseDBModel, table=True):
    """Insight 定时报告生成与企业微信推送计划。"""

    __tablename__ = "insight_report_subscription"

    subscription_uid: str = Field(index=True, unique=True, max_length=64)
    subscription_name: str = Field(index=True, max_length=160)
    report_type: str = Field(default="专题报告", index=True, max_length=50)
    template_code: str | None = Field(default=None, index=True, max_length=80)
    scope_type: str = Field(default="material_pool", index=True, max_length=30)
    sys_company_id: int | None = Field(default=None, foreign_key="sys_company.id", index=True)
    company_ids_json: list[int] = Field(default_factory=list, sa_type=JSONB)
    data_source_ids_json: list[int] = Field(default_factory=list, sa_type=JSONB)
    folder_name: str | None = Field(default="P1企业档案测试素材", max_length=100)
    max_materials: int = Field(default=100)
    generation_prompt: str | None = Field(default=None)
    schedule_frequency: str = Field(default="weekly", index=True, max_length=30)
    weekday: int | None = Field(default=0)
    day_of_month: int | None = Field(default=1)
    time_of_day: str = Field(default="09:00", max_length=5)
    timezone: str = Field(default="Asia/Shanghai", max_length=60)
    next_run_time: datetime | None = Field(default=None, index=True)
    last_run_time: datetime | None = Field(default=None, index=True)
    last_report_id: int | None = Field(default=None, foreign_key="insight_report.id", index=True)
    last_notification_id: int | None = Field(default=None, foreign_key="insight_notification.id", index=True)
    last_status: str | None = Field(default=None, index=True, max_length=30)
    last_error: str | None = Field(default=None, max_length=1000)
    wecom_recipient_scope: str = Field(default="selected", max_length=30)
    wecom_recipients_json: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    owner_user_id: int | None = Field(default=None, index=True)
    owner_dept_id: int | None = Field(default=None, index=True)
    visibility_scope: str = Field(default="private", index=True, max_length=30)
    status: str = Field(default="active", index=True, max_length=30)
