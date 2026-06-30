from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightReport(BaseDBModel, table=True):
    """Insight 报告草稿主表。"""

    __tablename__ = "insight_report"

    report_uid: str = Field(index=True, unique=True, max_length=64)
    title: str = Field(index=True, max_length=300)
    report_type: str = Field(default="专题报告", index=True, max_length=50)
    period_start: datetime | None = Field(default=None, index=True)
    period_end: datetime | None = Field(default=None, index=True)
    company_id: int | None = Field(default=None, foreign_key="insight_company.id", index=True)
    company_name: str | None = Field(default=None, index=True, max_length=200)
    content_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    summary: str | None = Field(default=None)
    status: str = Field(default="draft", index=True, max_length=30)
    version_no: int = Field(default=1)
    material_count: int = Field(default=0)
    owner_user_id: int | None = Field(default=None, index=True)
    owner_dept_id: int | None = Field(default=None, index=True)
    visibility_scope: str = Field(default="private", index=True, max_length=30)


class InsightReportMaterial(BaseDBModel, table=True):
    """报告引用的情报证据。"""

    __tablename__ = "insight_report_material"

    report_id: int = Field(foreign_key="insight_report.id", index=True)
    intelligence_id: int = Field(foreign_key="insight_intelligence.id", index=True)
    section_key: str = Field(default="key_findings", index=True, max_length=80)
    sort_no: int = Field(default=0, index=True)
    quote_text: str | None = Field(default=None)
    source_url: str | None = Field(default=None, max_length=1000)
    source_title: str | None = Field(default=None, max_length=500)
    selection_source: str = Field(default="report_material_pool", index=True, max_length=50)
    selection_reason: str | None = Field(default=None)


class InsightReportVersion(BaseDBModel, table=True):
    """报告版本快照。"""

    __tablename__ = "insight_report_version"

    report_id: int = Field(foreign_key="insight_report.id", index=True)
    version_no: int = Field(index=True)
    content_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    change_summary: str | None = Field(default=None)
    created_by_user_id: int | None = Field(default=None, index=True)


class InsightReportExport(BaseDBModel, table=True):
    """Insight 报告导出记录。"""

    __tablename__ = "insight_report_export"

    export_uid: str = Field(index=True, unique=True, max_length=64)
    report_id: int = Field(foreign_key="insight_report.id", index=True)
    report_version_no: int = Field(default=1, index=True)
    export_format: str = Field(default="html", index=True, max_length=30)
    status: str = Field(default="pending", index=True, max_length=30)
    file_name: str | None = Field(default=None, max_length=300)
    file_path: str | None = Field(default=None, max_length=1000)
    file_size: int | None = Field(default=None)
    content_type: str | None = Field(default=None, max_length=120)
    storage_backend: str = Field(default="local", max_length=30)
    error_message: str | None = Field(default=None, max_length=1000)
    requested_by_user_id: int | None = Field(default=None, index=True)
    finished_at: datetime | None = Field(default=None, index=True)


class InsightReportTemplate(BaseDBModel, table=True):
    """用户自定义报告模板。"""

    __tablename__ = "insight_report_template"

    template_code: str = Field(index=True, unique=True, max_length=80)
    template_name: str = Field(index=True, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    report_type: str = Field(default="专题报告", index=True, max_length=50)
    default_prompt: str | None = Field(default=None)
    sections_json: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    structure_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    template_kind: str = Field(default="document", index=True, max_length=30)
    style_code: str | None = Field(default=None, index=True, max_length=80)
    export_formats: list[str] = Field(default_factory=list, sa_type=JSONB)
    source_file_name: str | None = Field(default=None, max_length=300)
    source_file_type: str | None = Field(default=None, max_length=30)
    source_file_size: int | None = Field(default=None)
    scope: str = Field(default="personal", index=True, max_length=30)
    market_status: str = Field(default="not_listed", index=True, max_length=30)
    market_category: str | None = Field(default=None, index=True, max_length=80)
    market_description: str | None = Field(default=None, max_length=1000)
    cloned_from_template_id: int | None = Field(default=None, foreign_key="insight_report_template.id", index=True)
    published_at: datetime | None = Field(default=None, index=True)
    published_by_user_id: int | None = Field(default=None, index=True)
    owner_user_id: int | None = Field(default=None, index=True)
    owner_dept_id: int | None = Field(default=None, index=True)
    visibility_scope: str = Field(default="private", index=True, max_length=30)
    status: str = Field(default="active", index=True, max_length=30)


class InsightReportPreference(BaseDBModel, table=True):
    """用户报告生成偏好。"""

    __tablename__ = "insight_report_preference"

    user_id: int = Field(index=True, unique=True)
    default_template_code: str | None = Field(default=None, max_length=80)
    default_report_type: str = Field(default="专题报告", max_length=50)
    default_folder_name: str | None = Field(default=None, max_length=100)
    default_max_materials: int = Field(default=100)
    writing_stance: str = Field(default="客户经营视角", max_length=80)
    report_depth: str = Field(default="深度研究", max_length=50)
    citation_style: str = Field(default="正文上标引用", max_length=50)
    include_risks: bool = Field(default=True)
    include_opportunities: bool = Field(default=True)
    include_follow_up_questions: bool = Field(default=True)
    custom_prompt_suffix: str | None = Field(default=None)
    status: str = Field(default="active", index=True, max_length=30)
