from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightReviewRecord(BaseDBModel, table=True):
    """情报人工审核记录。"""

    __tablename__ = "insight_review_record"

    intelligence_id: int | None = Field(default=None, foreign_key="insight_intelligence.id", index=True)
    candidate_id: int | None = Field(default=None, foreign_key="insight_intelligence_candidate.id", index=True)
    review_user_id: int | None = Field(default=None, index=True)
    from_status: str | None = Field(default=None, max_length=30)
    to_status: str = Field(index=True, max_length=30)
    review_comment: str | None = Field(default=None)
    diff_json: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
