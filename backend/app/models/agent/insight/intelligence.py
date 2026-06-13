from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.agent.insight.enums import (
    InsightCandidateReviewStatus,
    InsightSubjectType,
    InsightVisibilityScope,
)
from app.models.base import BaseDBModel


class InsightIntelligence(BaseDBModel, table=True):
    """正式情报主表。"""

    __tablename__ = "insight_intelligence"

    intelligence_uid: str = Field(index=True, unique=True, max_length=64)
    title: str = Field(index=True, max_length=500)
    summary: str | None = Field(default=None)
    content: str | None = Field(default=None)
    company_id: int | None = Field(default=None, foreign_key="insight_company.id", index=True)
    subject_type: InsightSubjectType = Field(default=InsightSubjectType.COMPANY, index=True)
    subject_id: int | None = Field(default=None, index=True)
    subject_name: str | None = Field(default=None, index=True, max_length=200)
    data_source_id: int | None = Field(default=None, foreign_key="insight_data_source.id", index=True)
    intelligence_type: str = Field(index=True, max_length=50)
    business_domain: str | None = Field(default=None, index=True, max_length=100)
    importance_level: str = Field(default="medium", index=True, max_length=20)
    sentiment: str = Field(default="neutral", index=True, max_length=20)
    publish_time: datetime | None = Field(default=None, index=True)
    capture_time: datetime | None = Field(default=None, index=True)
    review_status: str = Field(default="pending", index=True, max_length=30)
    review_user_id: int | None = Field(default=None, index=True)
    review_time: datetime | None = Field(default=None, index=True)
    dedupe_hash: str | None = Field(default=None, index=True, max_length=128)
    visibility_scope: InsightVisibilityScope = Field(default=InsightVisibilityScope.ASSIGNED, index=True)
    owner_user_id: int | None = Field(default=None, index=True)
    raw_payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    status: str = Field(default="active", index=True, max_length=20)


class InsightIntelligenceSource(BaseDBModel, table=True):
    """正式情报来源证据。"""

    __tablename__ = "insight_intelligence_source"

    intelligence_id: int = Field(foreign_key="insight_intelligence.id", index=True)
    data_source_id: int | None = Field(default=None, foreign_key="insight_data_source.id", index=True)
    source_type: str = Field(index=True, max_length=50)
    source_url: str | None = Field(default=None, index=True, max_length=1000)
    source_title: str | None = Field(default=None, max_length=500)
    source_author: str | None = Field(default=None, max_length=200)
    source_publish_time: datetime | None = Field(default=None, index=True)
    content_excerpt: str | None = Field(default=None)
    file_object_path: str | None = Field(default=None, max_length=800)
    credibility_score: float = Field(default=0.7)
    source_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSONB)


class InsightIntelligenceCandidate(BaseDBModel, table=True):
    """采集结果抽取出的候选情报，审核后可转为正式情报。"""

    __tablename__ = "insight_intelligence_candidate"

    crawl_result_id: int = Field(foreign_key="insight_crawl_result.id", index=True)
    candidate_title: str = Field(index=True, max_length=500)
    candidate_summary: str | None = Field(default=None)
    subject_type: InsightSubjectType = Field(default=InsightSubjectType.CUSTOM, index=True)
    subject_name: str | None = Field(default=None, index=True, max_length=200)
    company_id: int | None = Field(default=None, foreign_key="insight_company.id", index=True)
    intelligence_type: str | None = Field(default=None, index=True, max_length=50)
    suggested_tags: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB)
    confidence: float = Field(default=0.0)
    promoted_intelligence_id: int | None = Field(default=None, foreign_key="insight_intelligence.id", index=True)
    review_status: InsightCandidateReviewStatus = Field(default=InsightCandidateReviewStatus.PENDING, index=True)
    status: str = Field(default="active", index=True, max_length=20)
