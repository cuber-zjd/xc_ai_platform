from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class InsightCompany(BaseDBModel, table=True):
    """研发营销市场洞察平台监控企业。"""

    __tablename__ = "insight_company"

    company_code: str = Field(index=True, unique=True, max_length=64)
    sys_company_id: int | None = Field(default=None, foreign_key="sys_company.id", index=True)
    name: str = Field(index=True, max_length=200)
    short_name: str | None = Field(default=None, index=True, max_length=100)
    industry: str | None = Field(default=None, index=True, max_length=100)
    company_type: str | None = Field(default=None, index=True, max_length=50)
    region: str | None = Field(default=None, index=True, max_length=100)
    website: str | None = Field(default=None, max_length=500)
    logo_url: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None)
    monitor_level: str = Field(default="normal", index=True, max_length=20)
    owner_user_id: int | None = Field(default=None, index=True)
    profile_json: dict[str, Any] | None = Field(default=None, sa_type=JSONB)
    status: str = Field(default="active", index=True, max_length=20)
