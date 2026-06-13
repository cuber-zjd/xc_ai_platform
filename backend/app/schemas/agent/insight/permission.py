from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightAccessRuleUpsert(BaseModel):
    principal_type: str = Field(..., min_length=1, max_length=30)
    principal_id: int | None = None
    permission: str = Field(default="view", max_length=30)
    grant_type: str = Field(default="manual", max_length=30)
    effective_from: datetime | None = None
    effective_to: datetime | None = None


class InsightAccessRuleRead(InsightBaseRead):
    target_type: str
    target_id: int
    principal_type: str
    principal_id: int | None = None
    permission: str
    grant_type: str
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    status: str


class InsightAccessRuleList(BaseModel):
    target_type: str
    target_id: int
    rules: list[InsightAccessRuleRead] = Field(default_factory=list)
