from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.agent.insight.enums import InsightTaskStatus
from app.models.base import BaseDBModel


class InsightTask(BaseDBModel, table=True):
    """采集、清洗、AI 分析、报告生成等统一任务记录。"""

    __tablename__ = "insight_task"

    task_uid: str = Field(index=True, unique=True, max_length=64)
    task_type: str = Field(index=True, max_length=50)
    data_source_id: int | None = Field(default=None, foreign_key="insight_data_source.id", index=True)
    intelligence_id: int | None = Field(default=None, foreign_key="insight_intelligence.id", index=True)
    report_id: int | None = Field(default=None, index=True)
    status: InsightTaskStatus = Field(default=InsightTaskStatus.PENDING, index=True)
    progress: int = Field(default=0)
    started_at: datetime | None = Field(default=None, index=True)
    finished_at: datetime | None = Field(default=None, index=True)
    retry_count: int = Field(default=0)
    input_payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    output_payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    error_message: str | None = Field(default=None)
