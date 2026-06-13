from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightIntelligenceCandidateRead(InsightBaseRead):
    crawl_result_id: int
    candidate_title: str
    candidate_summary: str | None = None
    subject_type: str
    subject_name: str | None = None
    company_id: int | None = None
    intelligence_type: str | None = None
    suggested_tags: list[dict[str, Any]] | None = None
    quality_report: dict[str, Any] | None = None
    quality_score: float | None = None
    quality_issues: list[str] = Field(default_factory=list)
    quality_auto_ignore: bool = False
    confidence: float
    promoted_intelligence_id: int | None = None
    review_status: str
    status: str


class InsightIntelligenceCandidateListItem(InsightIntelligenceCandidateRead):
    source_url: str | None = None
    source_title: str | None = None
    source_channel: str | None = None
    source_publish_time: datetime | None = None
    query_text: str | None = None


class InsightIntelligenceRead(InsightBaseRead):
    intelligence_uid: str
    title: str
    summary: str | None = None
    company_id: int | None = None
    subject_type: str
    subject_id: int | None = None
    subject_name: str | None = None
    intelligence_type: str
    business_domain: str | None = None
    importance_level: str
    sentiment: str
    publish_time: datetime | None = None
    capture_time: datetime | None = None
    review_status: str
    visibility_scope: str
    status: str


class InsightIntelligenceSourceRead(InsightBaseRead):
    intelligence_id: int
    data_source_id: int | None = None
    source_type: str
    source_url: str | None = None
    source_title: str | None = None
    source_author: str | None = None
    source_publish_time: datetime | None = None
    content_excerpt: str | None = None
    file_object_path: str | None = None
    credibility_score: float
    source_metadata: dict[str, Any] | None = None


class InsightIntelligenceListItem(InsightIntelligenceRead):
    primary_source_url: str | None = None
    primary_source_title: str | None = None
    primary_source_type: str | None = None
    source_count: int = 0
    suggested_tags: list[dict[str, Any]] | None = None


class InsightIntelligenceDetail(InsightIntelligenceRead):
    content: str | None = None
    raw_payload: dict[str, Any] | None = None
    sources: list[InsightIntelligenceSourceRead] = Field(default_factory=list)


class InsightIntelligenceSourceCreate(BaseModel):
    data_source_id: int | None = None
    source_type: str = Field(default="manual", min_length=1, max_length=50)
    source_url: str | None = Field(default=None, max_length=1000)
    source_title: str | None = Field(default=None, max_length=500)
    source_author: str | None = Field(default=None, max_length=200)
    source_publish_time: datetime | None = None
    content_excerpt: str | None = None
    file_object_path: str | None = Field(default=None, max_length=800)
    credibility_score: float = Field(default=0.7, ge=0, le=1)
    source_metadata: dict[str, Any] | None = None


class InsightIntelligenceSourceUpdate(BaseModel):
    data_source_id: int | None = None
    source_type: str | None = Field(default=None, max_length=50)
    source_url: str | None = Field(default=None, max_length=1000)
    source_title: str | None = Field(default=None, max_length=500)
    source_author: str | None = Field(default=None, max_length=200)
    source_publish_time: datetime | None = None
    content_excerpt: str | None = None
    file_object_path: str | None = Field(default=None, max_length=800)
    credibility_score: float | None = Field(default=None, ge=0, le=1)
    source_metadata: dict[str, Any] | None = None


class InsightIntelligenceCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    summary: str | None = None
    content: str | None = None
    company_id: int | None = None
    subject_type: str = Field(default="custom", max_length=30)
    subject_id: int | None = None
    subject_name: str | None = Field(default=None, max_length=200)
    data_source_id: int | None = None
    intelligence_type: str = Field(default="行业资讯", max_length=50)
    business_domain: str | None = Field(default=None, max_length=100)
    importance_level: str = Field(default="medium", max_length=20)
    sentiment: str = Field(default="neutral", max_length=20)
    publish_time: datetime | None = None
    visibility_scope: str = Field(default="assigned", max_length=30)
    suggested_tags: list[dict[str, Any]] | None = None
    source: InsightIntelligenceSourceCreate | None = None


class InsightIntelligenceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    summary: str | None = None
    content: str | None = None
    company_id: int | None = None
    subject_type: str | None = Field(default=None, max_length=30)
    subject_id: int | None = None
    subject_name: str | None = Field(default=None, max_length=200)
    data_source_id: int | None = None
    intelligence_type: str | None = Field(default=None, max_length=50)
    business_domain: str | None = Field(default=None, max_length=100)
    importance_level: str | None = Field(default=None, max_length=20)
    sentiment: str | None = Field(default=None, max_length=20)
    publish_time: datetime | None = None
    visibility_scope: str | None = Field(default=None, max_length=30)
    suggested_tags: list[dict[str, Any]] | None = None
    status: str | None = Field(default=None, max_length=20)


class InsightVisibilityRuleCreate(BaseModel):
    principal_type: str = Field(..., min_length=1, max_length=30)
    principal_id: int | None = None
    permission: str = Field(default="view", max_length=30)
    grant_type: str = Field(default="manual", max_length=30)
    effective_from: datetime | None = None
    effective_to: datetime | None = None


class InsightVisibilityRuleRead(InsightBaseRead):
    target_type: str
    target_id: int
    principal_type: str
    principal_id: int | None = None
    permission: str
    grant_type: str
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    status: str


class InsightPoolUpsertRequest(BaseModel):
    pool_type: str = Field(default="favorite", max_length=30)
    folder_name: str | None = Field(default=None, max_length=100)
    note: str | None = None


class InsightUserIntelligencePoolRead(InsightBaseRead):
    user_id: int
    intelligence_id: int
    pool_type: str
    folder_name: str | None = None
    note: str | None = None
    sort_no: int
    status: str


class InsightCandidateReviewRequest(BaseModel):
    review_comment: str | None = Field(default=None, max_length=1000)


class InsightCandidatePromoteRequest(InsightCandidateReviewRequest):
    visibility_scope: str = Field(default="assigned", max_length=30)
    importance_level: str = Field(default="medium", max_length=20)
    business_domain: str | None = Field(default=None, max_length=100)


class InsightCandidateReviewResponse(BaseModel):
    candidate: InsightIntelligenceCandidateRead
    intelligence: InsightIntelligenceRead | None = None
