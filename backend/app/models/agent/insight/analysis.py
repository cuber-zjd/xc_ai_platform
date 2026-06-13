from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightAiAnalysis(BaseDBModel, table=True):
    """情报 AI 分析结果。"""

    __tablename__ = "insight_ai_analysis"

    intelligence_id: int = Field(foreign_key="insight_intelligence.id", index=True)
    analysis_type: str = Field(index=True, max_length=50)
    model_code: str | None = Field(default=None, index=True, max_length=100)
    prompt_version: str | None = Field(default=None, index=True, max_length=64)
    summary: str | None = Field(default=None)
    opportunities: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB)
    risks: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB)
    suggested_tags: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB)
    impact_assessment: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    confidence: float = Field(default=0.0)
    status: str = Field(default="pending", index=True, max_length=20)
    error_message: str | None = Field(default=None)
