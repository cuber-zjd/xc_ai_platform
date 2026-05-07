from enum import Enum
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class FrAiReportTaskStatus(str, Enum):
    GENERATING = "generating"
    GENERATED = "generated"
    VALIDATING = "validating"
    VALIDATED = "validated"
    VALIDATION_FAILED = "validation_failed"
    PUBLISHED = "published"
    FAILED = "failed"


class FrAiReportTask(BaseDBModel, table=True):
    __tablename__ = "fr_ai_report_task"

    task_id: str = Field(index=True, unique=True)
    conversation_id: str | None = Field(default=None, index=True)
    parent_task_id: str | None = Field(default=None, index=True)
    revision_no: int = Field(default=1, index=True)
    report_name: str = Field(index=True)
    report_type: str | None = Field(default=None, index=True)
    status: FrAiReportTaskStatus = Field(default=FrAiReportTaskStatus.GENERATING)
    data_source_status: str | None = Field(default=None)

    source_file_name: str | None = None
    source_table_name: str | None = None
    requirement_text: str | None = None
    table_schema: dict[str, Any] | None = Field(default=None, sa_type=JSONB)

    excel_analysis: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    requirement_summary: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    report_dsl: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    query_sql: str | None = None
    sql_validation: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    create_table_sql: str | None = None
    generation_log: list[str] = Field(default_factory=list, sa_type=JSONB)

    cpt_object_path: str | None = None
    dsl_object_path: str | None = None
    sql_object_path: str | None = None
    create_sql_object_path: str | None = None
    log_object_path: str | None = None
    preview_url: str | None = None

    errors: list[str] = Field(default_factory=list, sa_type=JSONB)
    warnings: list[str] = Field(default_factory=list, sa_type=JSONB)


class FrAiReportConversation(BaseDBModel, table=True):
    __tablename__ = "fr_ai_report_conversation"

    conversation_id: str = Field(index=True, unique=True)
    title: str = Field(index=True)
    user_id: str | None = Field(default=None, index=True)
    latest_task_id: str | None = Field(default=None, index=True)
    status: str = Field(default="active", index=True)
    source_table_name: str | None = Field(default=None, index=True)
    summary: dict[str, Any] | None = Field(default=None, sa_type=JSONB)


class FrAiReportFeedback(BaseDBModel, table=True):
    __tablename__ = "fr_ai_report_feedback"

    feedback_id: str = Field(index=True, unique=True)
    conversation_id: str | None = Field(default=None, index=True)
    task_id: str = Field(index=True)
    feedback_type: str = Field(default="note", index=True)
    content: str
    payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    is_positive: bool | None = Field(default=None, index=True)
