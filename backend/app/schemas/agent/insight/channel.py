from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightChannelCreate(BaseModel):
    channel_code: str | None = Field(default=None, max_length=64)
    channel_name: str = Field(..., min_length=1, max_length=200)
    channel_type: str = Field(..., min_length=1, max_length=50)
    channel_url: str | None = Field(default=None, max_length=1000)
    applicable_scenarios: list[str] = Field(default_factory=list)
    collection_method: str = Field(default="search", max_length=50)
    login_requirement: str = Field(default="none", max_length=50)
    access_status: str = Field(default="pending", max_length=50)
    default_trust_level: str = Field(default="medium", max_length=20)
    default_frequency: str = Field(default="manual", max_length=30)
    default_processing_policy: str = Field(default="ai_review", max_length=50)
    config_json: dict[str, Any] | None = None
    sort_no: int = 0
    comment: str | None = Field(default=None, max_length=1000)
    status: str = Field(default="active", max_length=20)


class InsightChannelUpdate(BaseModel):
    channel_name: str | None = Field(default=None, min_length=1, max_length=200)
    channel_type: str | None = Field(default=None, min_length=1, max_length=50)
    channel_url: str | None = Field(default=None, max_length=1000)
    applicable_scenarios: list[str] | None = None
    collection_method: str | None = Field(default=None, max_length=50)
    login_requirement: str | None = Field(default=None, max_length=50)
    access_status: str | None = Field(default=None, max_length=50)
    default_trust_level: str | None = Field(default=None, max_length=20)
    default_frequency: str | None = Field(default=None, max_length=30)
    default_processing_policy: str | None = Field(default=None, max_length=50)
    config_json: dict[str, Any] | None = None
    sort_no: int | None = None
    comment: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, max_length=20)


class InsightChannelRead(InsightBaseRead):
    channel_code: str
    channel_name: str
    channel_type: str
    channel_url: str | None = None
    applicable_scenarios: list[str] = Field(default_factory=list)
    collection_method: str
    login_requirement: str
    access_status: str
    default_trust_level: str
    default_frequency: str
    default_processing_policy: str
    config_json: dict[str, Any] | None = None
    sort_no: int
    status: str
    comment: str | None = None
