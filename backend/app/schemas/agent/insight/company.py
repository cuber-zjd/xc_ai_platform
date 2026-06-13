from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightCompanyCreate(BaseModel):
    company_code: str | None = Field(default=None, max_length=64)
    sys_company_id: int | None = None
    name: str = Field(..., min_length=1, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    company_type: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=500)
    logo_url: str | None = Field(default=None, max_length=500)
    description: str | None = None
    monitor_level: str = Field(default="normal", max_length=20)
    owner_user_id: int | None = None
    profile_json: dict[str, Any] | None = None
    status: str = Field(default="active", max_length=20)


class InsightCompanyUpdate(BaseModel):
    sys_company_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    company_type: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=500)
    logo_url: str | None = Field(default=None, max_length=500)
    description: str | None = None
    monitor_level: str | None = Field(default=None, max_length=20)
    owner_user_id: int | None = None
    profile_json: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=20)


class InsightCompanyRead(InsightBaseRead):
    company_code: str
    sys_company_id: int | None = None
    name: str
    short_name: str | None = None
    industry: str | None = None
    company_type: str | None = None
    region: str | None = None
    website: str | None = None
    logo_url: str | None = None
    description: str | None = None
    monitor_level: str
    owner_user_id: int | None = None
    profile_json: dict[str, Any] | None = None
    status: str


class InsightCompanyImportError(BaseModel):
    row_no: int
    reason: str


class InsightCompanyImportResponse(BaseModel):
    total_rows: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: list[InsightCompanyImportError] = Field(default_factory=list)
    companies: list[InsightCompanyRead] = Field(default_factory=list)


class InsightCompanyListItem(InsightCompanyRead):
    intelligence_count: int = 0
    candidate_count: int = 0
    data_source_count: int = 0
    latest_intelligence_time: datetime | None = None


class InsightCompanyMetric(BaseModel):
    key: str
    label: str
    value: int
    compare_label: str = ""
    delta: int = 0


class InsightCompanyTypeSlice(BaseModel):
    label: str
    count: int
    percent: float


class InsightCompanyTagStat(BaseModel):
    name: str
    count: int


class InsightCompanyDataSourceSummary(BaseModel):
    id: int
    source_name: str
    source_type: str
    status: str
    last_success_time: datetime | None = None


class InsightCompanyTimelineItem(BaseModel):
    id: int
    title: str
    summary: str | None = None
    intelligence_type: str
    importance_level: str
    publish_time: datetime | None = None
    create_time: datetime
    primary_source_url: str | None = None
    primary_source_title: str | None = None


class InsightCompanyDetail(InsightCompanyRead):
    metrics: list[InsightCompanyMetric] = Field(default_factory=list)
    type_distribution: list[InsightCompanyTypeSlice] = Field(default_factory=list)
    tag_stats: list[InsightCompanyTagStat] = Field(default_factory=list)
    data_sources: list[InsightCompanyDataSourceSummary] = Field(default_factory=list)
    timeline: list[InsightCompanyTimelineItem] = Field(default_factory=list)
