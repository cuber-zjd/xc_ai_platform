from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightDataSource(BaseDBModel, table=True):
    """情报采集数据源配置。"""

    __tablename__ = "insight_data_source"

    source_code: str = Field(index=True, unique=True, max_length=64)
    source_name: str = Field(index=True, max_length=200)
    source_type: str = Field(index=True, max_length=50)
    base_url: str | None = Field(default=None, max_length=1000)
    company_id: int | None = Field(default=None, foreign_key="insight_company.id", index=True)
    fetch_frequency: str = Field(default="manual", max_length=50)
    fetch_config: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    auth_config_ref: str | None = Field(default=None, max_length=200)
    last_fetch_time: datetime | None = Field(default=None, index=True)
    last_success_time: datetime | None = Field(default=None, index=True)
    next_run_time: datetime | None = Field(default=None, index=True)
    schedule_enabled: bool = Field(default=False, index=True)
    last_schedule_status: str | None = Field(default=None, max_length=30)
    last_schedule_message: str | None = Field(default=None, max_length=1000)
    consecutive_failure_count: int = Field(default=0)
    last_failure_time: datetime | None = Field(default=None, index=True)
    auto_paused_reason: str | None = Field(default=None, max_length=1000)
    owner_user_id: int | None = Field(default=None, index=True)
    owner_dept_id: int | None = Field(default=None, index=True)
    visibility_scope: str = Field(default="private", index=True, max_length=30)
    status: str = Field(default="enabled", index=True, max_length=20)
