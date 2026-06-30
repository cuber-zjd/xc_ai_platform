from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightAiReviewDecision(BaseModel):
    decision: str = Field(default="candidate", max_length=30)
    score: float = Field(default=0.0, ge=0, le=1)
    reason: str | None = None
    intelligence_type_code: str | None = None
    intelligence_type: str | None = None
    business_value: str | None = None
    tag_codes: list[str] = Field(default_factory=list)
    tag_names: list[str] = Field(default_factory=list)
    suggested_new_tags: list[str] = Field(default_factory=list)
    related_products: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    evidence: str | None = None


class InsightAiReviewResponse(BaseModel):
    candidate_id: int
    decision: InsightAiReviewDecision
    candidate_status: str
    intelligence_id: int | None = None
    asset_id: int | None = None


class InsightAssetRead(InsightBaseRead):
    asset_uid: str
    asset_type: str
    source_kind: str
    intelligence_id: int | None = None
    candidate_id: int | None = None
    crawl_result_id: int | None = None
    data_source_id: int | None = None
    company_id: int | None = None
    subject_type: str
    subject_id: int | None = None
    subject_name: str | None = None
    title: str
    summary: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    source_channel: str | None = None
    publish_time: datetime | None = None
    intelligence_type: str | None = None
    business_value: str | None = None
    importance_level: str
    sentiment: str
    confidence: float
    tags: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    related_products: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    evidence: str | None = None
    review_reason: str | None = None
    embedding_status: str
    graph_status: str
    visibility_scope: str
    status: str


class InsightAssetSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=8, ge=1, le=30)
    include_candidates: bool = False
    company_id: int | None = None
    subject_type: str | None = Field(default=None, max_length=30)
    intelligence_type: str | None = Field(default=None, max_length=50)
    date_from: datetime | None = None
    date_to: datetime | None = None


class InsightAssetSearchHit(BaseModel):
    asset: InsightAssetRead
    score: float
    vector_score: float | None = None
    keyword_score: float | None = None
    match_reason: str | None = None


class InsightAssetSearchResponse(BaseModel):
    query: str
    hits: list[InsightAssetSearchHit] = Field(default_factory=list)
    generation_mode: str = "asset_rag"


class InsightFormalAssetBackfillRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    include_inactive: bool = False
    reindex_existing_failed: bool = False


class InsightFormalAssetBackfillResponse(BaseModel):
    requested_limit: int
    scanned_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    indexed_count: int = 0
    failed_count: int = 0
    remaining_count: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)


class InsightGraphNodeRead(InsightBaseRead):
    node_uid: str
    node_type: str
    node_name: str
    canonical_name: str | None = None
    source_asset_id: int | None = None
    company_id: int | None = None
    node_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str


class InsightGraphEdgeRead(InsightBaseRead):
    edge_uid: str
    source_node_id: int
    target_node_id: int
    relation_type: str
    source_asset_id: int | None = None
    confidence: float
    evidence_text: str | None = None
    edge_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str


class InsightGraphResponse(BaseModel):
    nodes: list[InsightGraphNodeRead] = Field(default_factory=list)
    edges: list[InsightGraphEdgeRead] = Field(default_factory=list)
