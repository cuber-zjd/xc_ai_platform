from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.agent.insight.enums import InsightSubjectType, InsightVisibilityScope
from app.models.base import BaseDBModel


class InsightIntelligenceAsset(BaseDBModel, table=True):
    """情报资产统一索引表，连接候选、正式情报、原文证据和后续检索能力。"""

    __tablename__ = "insight_intelligence_asset"

    asset_uid: str = Field(index=True, unique=True, max_length=80)
    asset_type: str = Field(default="formal", index=True, max_length=30)
    source_kind: str = Field(default="intelligence", index=True, max_length=30)
    intelligence_id: int | None = Field(default=None, foreign_key="insight_intelligence.id", index=True)
    candidate_id: int | None = Field(default=None, foreign_key="insight_intelligence_candidate.id", index=True)
    crawl_result_id: int | None = Field(default=None, foreign_key="insight_crawl_result.id", index=True)
    data_source_id: int | None = Field(default=None, foreign_key="insight_data_source.id", index=True)
    company_id: int | None = Field(default=None, foreign_key="insight_company.id", index=True)
    subject_type: InsightSubjectType = Field(default=InsightSubjectType.CUSTOM, index=True)
    subject_id: int | None = Field(default=None, index=True)
    subject_name: str | None = Field(default=None, index=True, max_length=200)
    title: str = Field(index=True, max_length=500)
    summary: str | None = Field(default=None)
    evidence_text: str | None = Field(default=None)
    source_url: str | None = Field(default=None, index=True, max_length=1000)
    source_title: str | None = Field(default=None, max_length=500)
    source_channel: str | None = Field(default=None, index=True, max_length=50)
    publish_time: datetime | None = Field(default=None, index=True)
    intelligence_type: str | None = Field(default=None, index=True, max_length=50)
    business_value: str | None = Field(default=None, index=True, max_length=100)
    importance_level: str = Field(default="medium", index=True, max_length=20)
    sentiment: str = Field(default="neutral", index=True, max_length=20)
    confidence: float = Field(default=0.0, index=True)
    tags: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    entities: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONB)
    opportunities: list[str] = Field(default_factory=list, sa_type=JSONB)
    risks: list[str] = Field(default_factory=list, sa_type=JSONB)
    keywords: list[str] = Field(default_factory=list, sa_type=JSONB)
    structured_payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    review_payload: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    embedding_status: str = Field(default="pending", index=True, max_length=30)
    graph_status: str = Field(default="pending", index=True, max_length=30)
    visibility_scope: InsightVisibilityScope = Field(default=InsightVisibilityScope.ASSIGNED, index=True)
    owner_user_id: int | None = Field(default=None, index=True)
    owner_dept_id: int | None = Field(default=None, index=True)
    status: str = Field(default="active", index=True, max_length=20)


class InsightAssetVector(BaseDBModel, table=True):
    """情报资产向量索引。第一版存在 PostgreSQL，后续可迁移到 Milvus。"""

    __tablename__ = "insight_asset_vector"

    asset_id: int = Field(foreign_key="insight_intelligence_asset.id", index=True)
    vector_uid: str = Field(index=True, unique=True, max_length=100)
    vector_scope: str = Field(default="summary", index=True, max_length=30)
    embedding_model: str = Field(index=True, max_length=100)
    dimension: int = Field(default=0, index=True)
    content_hash: str = Field(index=True, max_length=128)
    vector: list[float] = Field(default_factory=list, sa_type=JSONB)
    vector_metadata: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    status: str = Field(default="indexed", index=True, max_length=20)


class InsightGraphNode(BaseDBModel, table=True):
    """轻量知识图谱节点。"""

    __tablename__ = "insight_graph_node"

    node_uid: str = Field(index=True, unique=True, max_length=100)
    node_type: str = Field(index=True, max_length=50)
    node_name: str = Field(index=True, max_length=300)
    canonical_name: str | None = Field(default=None, index=True, max_length=300)
    source_asset_id: int | None = Field(default=None, foreign_key="insight_intelligence_asset.id", index=True)
    company_id: int | None = Field(default=None, foreign_key="insight_company.id", index=True)
    node_metadata: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    status: str = Field(default="active", index=True, max_length=20)


class InsightGraphEdge(BaseDBModel, table=True):
    """轻量知识图谱关系。"""

    __tablename__ = "insight_graph_edge"

    edge_uid: str = Field(index=True, unique=True, max_length=120)
    source_node_id: int = Field(foreign_key="insight_graph_node.id", index=True)
    target_node_id: int = Field(foreign_key="insight_graph_node.id", index=True)
    relation_type: str = Field(index=True, max_length=80)
    source_asset_id: int | None = Field(default=None, foreign_key="insight_intelligence_asset.id", index=True)
    confidence: float = Field(default=0.6, index=True)
    evidence_text: str | None = Field(default=None)
    edge_metadata: dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)
    status: str = Field(default="active", index=True, max_length=20)
