from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.agent.insight.enums import InsightSubjectType
from app.models.base import BaseDBModel


class InsightSubject(BaseDBModel, table=True):
    """非企业主题，例如行业趋势、市场报告、政策或技术主题。"""

    __tablename__ = "insight_subject"

    subject_code: str = Field(index=True, unique=True, max_length=64)
    subject_name: str = Field(index=True, max_length=200)
    subject_type: InsightSubjectType = Field(default=InsightSubjectType.CUSTOM, index=True)
    parent_id: int | None = Field(default=None, foreign_key="insight_subject.id", index=True)
    description: str | None = Field(default=None)
    owner_user_id: int | None = Field(default=None, index=True)
    subject_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    status: str = Field(default="active", index=True, max_length=20)
