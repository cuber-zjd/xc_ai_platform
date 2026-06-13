from datetime import datetime

from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightVisibilityRule(BaseDBModel, table=True):
    """情报、主题、报告等对象的可见性规则。"""

    __tablename__ = "insight_visibility_rule"

    target_type: str = Field(index=True, max_length=30)
    target_id: int = Field(index=True)
    principal_type: str = Field(index=True, max_length=30)
    principal_id: int | None = Field(default=None, index=True)
    permission: str = Field(default="view", index=True, max_length=30)
    grant_type: str = Field(default="manual", index=True, max_length=30)
    effective_from: datetime | None = Field(default=None, index=True)
    effective_to: datetime | None = Field(default=None, index=True)
    status: str = Field(default="active", index=True, max_length=20)


class InsightUserIntelligencePool(BaseDBModel, table=True):
    """用户个人情报池，用于收藏、稍后看和报告候选素材。"""

    __tablename__ = "insight_user_intelligence_pool"

    user_id: int = Field(index=True)
    intelligence_id: int = Field(foreign_key="insight_intelligence.id", index=True)
    pool_type: str = Field(default="favorite", index=True, max_length=30)
    folder_name: str | None = Field(default=None, index=True, max_length=100)
    note: str | None = Field(default=None)
    sort_no: int = Field(default=0)
    status: str = Field(default="active", index=True, max_length=20)
