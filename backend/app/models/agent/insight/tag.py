from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightTag(BaseDBModel, table=True):
    """Insight 业务标签字典。"""

    __tablename__ = "insight_tag"

    tag_code: str = Field(index=True, unique=True, max_length=64)
    tag_name: str = Field(index=True, max_length=100)
    tag_type: str = Field(index=True, max_length=50)
    color: str | None = Field(default=None, max_length=50)
    sort_no: int = Field(default=0, index=True)
    status: str = Field(default="active", index=True, max_length=20)


class InsightTagCategory(BaseDBModel, table=True):
    """Insight 标签分类字典。"""

    __tablename__ = "insight_tag_category"

    category_code: str = Field(index=True, unique=True, max_length=64)
    category_name: str = Field(index=True, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = Field(default=None, max_length=50)
    sort_no: int = Field(default=0, index=True)
    status: str = Field(default="active", index=True, max_length=20)


class InsightIntelligenceTag(BaseDBModel, table=True):
    """情报与标签关系。"""

    __tablename__ = "insight_intelligence_tag"

    intelligence_id: int = Field(foreign_key="insight_intelligence.id", index=True)
    tag_id: int = Field(foreign_key="insight_tag.id", index=True)
    source: str = Field(default="manual", index=True, max_length=30)
    confidence: float = Field(default=1.0)
