from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightChannel(BaseDBModel, table=True):
    """Insight 渠道库，维护网站、数据库、平台等基础来源。"""

    __tablename__ = "insight_channel"

    channel_code: str = Field(index=True, unique=True, max_length=64)
    channel_name: str = Field(index=True, max_length=200)
    channel_type: str = Field(index=True, max_length=50)
    channel_url: str | None = Field(default=None, max_length=1000)
    applicable_scenarios: list[str] | None = Field(default=None, sa_type=JSONB)
    collection_method: str = Field(default="search", index=True, max_length=50)
    login_requirement: str = Field(default="none", index=True, max_length=50)
    access_status: str = Field(default="pending", index=True, max_length=50)
    default_trust_level: str = Field(default="medium", index=True, max_length=20)
    default_frequency: str = Field(default="manual", max_length=30)
    default_processing_policy: str = Field(default="ai_review", max_length=50)
    config_json: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    sort_no: int = Field(default=0, index=True)
    status: str = Field(default="active", index=True, max_length=20)
