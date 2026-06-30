from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead
from app.schemas.agent.insight.notification import InsightNotificationRecipient, InsightNotificationRead


class InsightReportGenerateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    report_type: str = Field(default="专题报告", max_length=50)
    template_code: str | None = Field(default=None, max_length=80)
    company_ids: list[int] = Field(default_factory=list)
    data_source_ids: list[int] = Field(default_factory=list)
    intelligence_ids: list[int] = Field(default_factory=list)
    folder_name: str | None = Field(default=None, max_length=100)
    period_start: datetime | None = None
    period_end: datetime | None = None
    max_materials: int = Field(default=60, ge=5, le=120)
    generation_prompt: str | None = Field(default=None, max_length=3000)


class InsightReportUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content_json: dict[str, Any] | None = None
    summary: str | None = None
    status: str | None = Field(default=None, max_length=30)
    change_summary: str | None = Field(default=None, max_length=300)


class InsightReportTemplateSection(BaseModel):
    section_key: str
    heading: str
    description: str


class InsightReportTemplateRead(BaseModel):
    template_code: str
    template_name: str
    description: str
    report_type: str
    default_prompt: str
    sections: list[InsightReportTemplateSection] = Field(default_factory=list)
    structure_json: dict[str, Any] = Field(default_factory=dict)
    template_kind: str = "document"
    style_code: str | None = None
    export_formats: list[str] = Field(default_factory=list)
    source_file_name: str | None = None
    source_file_type: str | None = None
    source_file_size: int | None = None
    scope: str = "system"
    market_status: str = "not_listed"
    market_category: str | None = None
    market_description: str | None = None
    cloned_from_template_id: int | None = None
    published_at: datetime | None = None
    published_by_user_id: int | None = None
    owner_user_id: int | None = None
    owner_dept_id: int | None = None
    visibility_scope: str = "private"
    editable: bool = False
    id: int | None = None


class InsightReportTemplateCreate(BaseModel):
    template_name: str = Field(max_length=120)
    description: str | None = Field(default=None, max_length=500)
    report_type: str = Field(default="专题报告", max_length=50)
    default_prompt: str = Field(max_length=3000)
    sections: list[InsightReportTemplateSection] = Field(default_factory=list)
    structure_json: dict[str, Any] | None = None
    template_kind: str = Field(default="document", max_length=30)
    style_code: str | None = Field(default=None, max_length=80)
    export_formats: list[str] = Field(default_factory=list)
    visibility_scope: str = Field(default="private", max_length=30)


class InsightReportTemplateUpdate(BaseModel):
    template_name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    report_type: str | None = Field(default=None, max_length=50)
    default_prompt: str | None = Field(default=None, max_length=3000)
    sections: list[InsightReportTemplateSection] | None = None
    structure_json: dict[str, Any] | None = None
    template_kind: str | None = Field(default=None, max_length=30)
    style_code: str | None = Field(default=None, max_length=80)
    export_formats: list[str] | None = None
    visibility_scope: str | None = Field(default=None, max_length=30)
    market_status: str | None = Field(default=None, max_length=30)
    market_category: str | None = Field(default=None, max_length=80)
    market_description: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, max_length=30)


class InsightReportTemplatePublishRequest(BaseModel):
    market_category: str | None = Field(default=None, max_length=80)
    market_description: str | None = Field(default=None, max_length=1000)


class InsightReportTemplateCloneRequest(BaseModel):
    template_name: str | None = Field(default=None, max_length=120)


class InsightReportTemplateUploadResponse(BaseModel):
    template: InsightReportTemplateRead
    parsed_structure: dict[str, Any] = Field(default_factory=dict)
    extracted_text_preview: str | None = None


class InsightReportPreferenceRead(InsightBaseRead):
    user_id: int
    default_template_code: str | None = None
    default_report_type: str
    default_folder_name: str | None = None
    default_max_materials: int
    writing_stance: str
    report_depth: str
    citation_style: str
    include_risks: bool
    include_opportunities: bool
    include_follow_up_questions: bool
    custom_prompt_suffix: str | None = None
    status: str


class InsightReportPreferenceUpdate(BaseModel):
    default_template_code: str | None = Field(default=None, max_length=80)
    default_report_type: str | None = Field(default=None, max_length=50)
    default_folder_name: str | None = Field(default=None, max_length=100)
    default_max_materials: int | None = Field(default=None, ge=5, le=120)
    writing_stance: str | None = Field(default=None, max_length=80)
    report_depth: str | None = Field(default=None, max_length=50)
    citation_style: str | None = Field(default=None, max_length=50)
    include_risks: bool | None = None
    include_opportunities: bool | None = None
    include_follow_up_questions: bool | None = None
    custom_prompt_suffix: str | None = Field(default=None, max_length=1500)


class InsightReportMaterialRead(InsightBaseRead):
    report_id: int
    intelligence_id: int
    section_key: str
    sort_no: int
    quote_text: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    selection_source: str
    selection_reason: str | None = None
    intelligence_title: str | None = None
    intelligence_summary: str | None = None


class InsightReportChartPoint(BaseModel):
    label: str
    value: int | float
    key: str | None = None
    percent: float | None = None


class InsightReportChartRead(BaseModel):
    chart_key: str
    title: str
    description: str | None = None
    chart_type: str = Field(default="bar", max_length=30)
    unit: str = Field(default="条", max_length=20)
    points: list[InsightReportChartPoint] = Field(default_factory=list)


class InsightReportVersionRead(InsightBaseRead):
    report_id: int
    version_no: int
    content_json: dict[str, Any]
    change_summary: str | None = None
    created_by_user_id: int | None = None


class InsightReportExportRequest(BaseModel):
    export_format: str = Field(default="html", max_length=30)


class InsightReportExportRead(InsightBaseRead):
    export_uid: str
    report_id: int
    report_version_no: int
    export_format: str
    status: str
    file_name: str | None = None
    file_size: int | None = None
    content_type: str | None = None
    storage_backend: str
    error_message: str | None = None
    requested_by_user_id: int | None = None
    finished_at: datetime | None = None


class InsightReportRead(InsightBaseRead):
    report_uid: str
    title: str
    report_type: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    company_id: int | None = None
    company_name: str | None = None
    content_json: dict[str, Any]
    summary: str | None = None
    status: str
    version_no: int
    material_count: int
    owner_user_id: int | None = None
    owner_dept_id: int | None = None
    visibility_scope: str = "private"


class InsightReportListItem(InsightReportRead):
    pass


class InsightReportDetail(InsightReportRead):
    materials: list[InsightReportMaterialRead] = Field(default_factory=list)
    versions: list[InsightReportVersionRead] = Field(default_factory=list)
    charts: list[InsightReportChartRead] = Field(default_factory=list)


class InsightReportGenerateResponse(BaseModel):
    report: InsightReportDetail
    task_id: int | None = None
    used_material_count: int
    generation_mode: str


class InsightReportSubscriptionBase(BaseModel):
    subscription_name: str = Field(max_length=160)
    report_type: str = Field(default="专题报告", max_length=50)
    template_code: str | None = Field(default=None, max_length=80)
    scope_type: str = Field(default="material_pool", max_length=30)
    sys_company_id: int | None = None
    company_ids: list[int] = Field(default_factory=list)
    data_source_ids: list[int] = Field(default_factory=list)
    folder_name: str | None = Field(default=None, max_length=100)
    max_materials: int = Field(default=100, ge=5, le=120)
    generation_prompt: str | None = Field(default=None, max_length=3000)
    schedule_frequency: str = Field(default="weekly", max_length=30)
    weekday: int | None = Field(default=0, ge=0, le=6)
    day_of_month: int | None = Field(default=1, ge=1, le=31)
    time_of_day: str = Field(default="09:00", max_length=5)
    timezone: str = Field(default="Asia/Shanghai", max_length=60)
    wecom_recipient_scope: str = Field(default="selected", max_length=30)
    wecom_recipients: list[InsightNotificationRecipient] = Field(default_factory=list)
    visibility_scope: str = Field(default="private", max_length=30)
    status: str = Field(default="active", max_length=30)


class InsightReportSubscriptionCreate(InsightReportSubscriptionBase):
    pass


class InsightReportSubscriptionUpdate(BaseModel):
    subscription_name: str | None = Field(default=None, max_length=160)
    report_type: str | None = Field(default=None, max_length=50)
    template_code: str | None = Field(default=None, max_length=80)
    scope_type: str | None = Field(default=None, max_length=30)
    sys_company_id: int | None = None
    company_ids: list[int] | None = None
    data_source_ids: list[int] | None = None
    folder_name: str | None = Field(default=None, max_length=100)
    max_materials: int | None = Field(default=None, ge=5, le=120)
    generation_prompt: str | None = Field(default=None, max_length=3000)
    schedule_frequency: str | None = Field(default=None, max_length=30)
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    time_of_day: str | None = Field(default=None, max_length=5)
    timezone: str | None = Field(default=None, max_length=60)
    wecom_recipient_scope: str | None = Field(default=None, max_length=30)
    wecom_recipients: list[InsightNotificationRecipient] | None = None
    visibility_scope: str | None = Field(default=None, max_length=30)
    status: str | None = Field(default=None, max_length=30)


class InsightReportSubscriptionRead(InsightBaseRead):
    subscription_uid: str
    subscription_name: str
    report_type: str
    template_code: str | None = None
    scope_type: str
    sys_company_id: int | None = None
    company_ids: list[int] = Field(default_factory=list)
    data_source_ids: list[int] = Field(default_factory=list)
    folder_name: str | None = None
    max_materials: int
    generation_prompt: str | None = None
    schedule_frequency: str
    weekday: int | None = None
    day_of_month: int | None = None
    time_of_day: str
    timezone: str
    next_run_time: datetime | None = None
    last_run_time: datetime | None = None
    last_report_id: int | None = None
    last_notification_id: int | None = None
    last_status: str | None = None
    last_error: str | None = None
    wecom_recipient_scope: str
    wecom_recipients: list[InsightNotificationRecipient] = Field(default_factory=list)
    owner_user_id: int | None = None
    owner_dept_id: int | None = None
    visibility_scope: str
    status: str


class InsightReportSubscriptionRunResponse(BaseModel):
    subscription: InsightReportSubscriptionRead
    report: InsightReportDetail | None = None
    notification: InsightNotificationRead | None = None
    skipped: bool = False
    message: str | None = None


class InsightReportSubscriptionDueRunResponse(BaseModel):
    checked_count: int
    due_count: int
    executed_count: int
    failed_count: int
    results: list[InsightReportSubscriptionRunResponse] = Field(default_factory=list)
