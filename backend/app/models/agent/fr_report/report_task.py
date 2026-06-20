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


class FrReportSnapshot(BaseDBModel, table=True):
    __tablename__ = "fr_report_snapshot"

    snapshot_id: str = Field(index=True, unique=True)
    object_path: str = Field(index=True)
    report_path: str | None = Field(default=None, index=True)
    file_name: str | None = None
    file_type: str | None = None
    user_id: int = Field(index=True)
    parent_snapshot_id: str | None = Field(default=None, index=True)
    source_etag: str | None = Field(default=None, index=True)
    source_last_modified: str | None = None
    snapshot_no: int = Field(default=1, index=True)
    status: str = Field(default="source_imported", index=True)
    title: str | None = None
    summary: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    document_snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    applied_patch: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    source_hash: str | None = Field(default=None, index=True)
    cpt_object_path: str | None = None
    meta_object_path: str | None = None
    preview_url: str | None = None
    generation_errors: list[str] = Field(default_factory=list, sa_type=JSONB)
    generation_warnings: list[str] = Field(default_factory=list, sa_type=JSONB)


class FrReportProject(BaseDBModel, table=True):
    __tablename__ = "fr_report_project"

    report_id: str = Field(index=True, unique=True)
    report_name: str = Field(index=True)
    report_code: str = Field(index=True)
    target_folder: str = Field(index=True)
    current_object_path: str = Field(index=True)
    current_structure_version_id: str | None = Field(default=None, index=True)
    current_file_version_id: str | None = Field(default=None, index=True)
    owner_user_id: int = Field(index=True)
    source_object_path: str | None = Field(default=None, index=True)
    status: str = Field(default="active", index=True)
    summary: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)


class FrReportStructureVersion(BaseDBModel, table=True):
    __tablename__ = "fr_report_structure_version"

    structure_version_id: str = Field(index=True, unique=True)
    report_id: str = Field(index=True)
    snapshot_id: str | None = Field(default=None, index=True)
    version_no: int = Field(default=1, index=True)
    version_name: str | None = None
    parent_version_id: str | None = Field(default=None, index=True)
    source_type: str = Field(default="ai_generated", index=True)
    report_dsl: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    document_snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    sql_snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    style_snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    writeback_snapshot: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    operation_patch: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    diff_summary: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    status: str = Field(default="active", index=True)


class FrReportFileVersion(BaseDBModel, table=True):
    __tablename__ = "fr_report_file_version"

    file_version_id: str = Field(index=True, unique=True)
    report_id: str = Field(index=True)
    structure_version_id: str | None = Field(default=None, index=True)
    version_no: int = Field(default=1, index=True)
    version_name: str | None = None
    current_object_path: str = Field(index=True)
    archive_object_path: str = Field(index=True)
    dsl_object_path: str | None = None
    manifest_object_path: str | None = None
    diff_object_path: str | None = None
    source_file_hash: str | None = Field(default=None, index=True)
    target_file_hash: str | None = Field(default=None, index=True)
    source_etag: str | None = Field(default=None, index=True)
    target_etag: str | None = Field(default=None, index=True)
    source_last_modified: str | None = None
    target_last_modified: str | None = None
    write_status: str = Field(default="generated", index=True)
    preview_url: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    warnings: list[str] = Field(default_factory=list, sa_type=JSONB)
    errors: list[str] = Field(default_factory=list, sa_type=JSONB)


class FrReportExternalChangeLog(BaseDBModel, table=True):
    __tablename__ = "fr_report_external_change_log"

    change_id: str = Field(index=True, unique=True)
    report_id: str = Field(index=True)
    object_path: str = Field(index=True)
    last_known_hash: str | None = Field(default=None, index=True)
    detected_hash: str | None = Field(default=None, index=True)
    last_known_etag: str | None = None
    detected_etag: str | None = None
    last_known_modified: str | None = None
    detected_modified: str | None = None
    base_file_version_id: str | None = Field(default=None, index=True)
    status: str = Field(default="detected", index=True)
    detail: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)


class FrReportOperationDraft(BaseDBModel, table=True):
    __tablename__ = "fr_report_operation_draft"

    draft_id: str = Field(index=True, unique=True)
    object_path: str = Field(index=True)
    user_id: int = Field(index=True)
    base_snapshot_id: str | None = Field(default=None, index=True)
    target_snapshot_id: str | None = Field(default=None, index=True)
    prompt: str | None = None
    selected_cell: str | None = Field(default=None, index=True)
    selected_dataset: str | None = Field(default=None, index=True)
    status: str = Field(default="draft", index=True)
    assistant_message: str | None = None
    operations: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    preview_patch: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    safety: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    warnings: list[str] = Field(default_factory=list, sa_type=JSONB)


class FrReportVisibilityPreference(BaseDBModel, table=True):
    __tablename__ = "fr_report_visibility_preference"

    user_id: int = Field(index=True, unique=True)
    visible_paths: list[str] = Field(default_factory=list, sa_type=JSONB)
    status: str = Field(default="active", index=True)


class FrReportDatabaseConnection(BaseDBModel, table=True):
    __tablename__ = "fr_report_database_connection"

    user_id: int = Field(index=True)
    connection_name: str = Field(index=True)
    driver_key: str = Field(default="sqlserver", index=True)
    db_type: str = Field(default="sqlserver", index=True)
    host: str
    port: int = Field(default=1433)
    database: str
    username: str
    password: str
    odbc_driver: str | None = None
    status: str = Field(default="active", index=True)


class FrReportDatabaseDriver(BaseDBModel, table=True):
    __tablename__ = "fr_report_database_driver"

    driver_key: str = Field(index=True, unique=True)
    display_name: str
    db_type: str = Field(index=True)
    python_driver: str
    odbc_driver: str | None = None
    default_port: int
    description: str | None = None
    status: str = Field(default="active", index=True)
