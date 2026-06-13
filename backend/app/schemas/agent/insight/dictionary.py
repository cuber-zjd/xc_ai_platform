from pydantic import BaseModel, Field

from app.schemas.agent.insight.common import InsightBaseRead


class InsightTagCreate(BaseModel):
    tag_code: str | None = Field(default=None, max_length=64)
    tag_name: str = Field(..., min_length=1, max_length=100)
    tag_type: str = Field(default="business", max_length=50)
    color: str | None = Field(default=None, max_length=50)
    sort_no: int = 0


class InsightTagUpdate(BaseModel):
    tag_name: str | None = Field(default=None, min_length=1, max_length=100)
    tag_type: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, max_length=50)
    sort_no: int | None = None
    status: str | None = Field(default=None, max_length=20)


class InsightTagRead(InsightBaseRead):
    tag_code: str
    tag_name: str
    tag_type: str
    color: str | None = None
    sort_no: int
    status: str


class InsightIntelligenceTypeRead(BaseModel):
    type_code: str
    type_name: str
    description: str
    sort_no: int
    status: str = "active"
    readonly: bool = True
    usage_count: int = 0


class InsightDictionaryOverview(BaseModel):
    tags: list[InsightTagRead] = Field(default_factory=list)
    intelligence_types: list[InsightIntelligenceTypeRead] = Field(default_factory=list)
