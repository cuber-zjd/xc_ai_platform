from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.agent.insight.intelligence import InsightIntelligenceListItem


class InsightDashboardMetric(BaseModel):
    key: str
    label: str
    value: int
    compare_label: str
    delta: int


class InsightDashboardTrendPoint(BaseModel):
    date: date
    label: str
    count: int


class InsightDashboardSourceSlice(BaseModel):
    source_type: str
    label: str
    count: int
    percent: float


class InsightDashboardFocusItem(BaseModel):
    id: int
    title: str
    subject_name: str | None = None
    intelligence_type: str
    importance_level: str
    publish_time: datetime | None = None
    score: int = Field(default=0)


class InsightDashboardSummary(BaseModel):
    metrics: list[InsightDashboardMetric] = Field(default_factory=list)
    trend: list[InsightDashboardTrendPoint] = Field(default_factory=list)
    source_distribution: list[InsightDashboardSourceSlice] = Field(default_factory=list)
    focus_items: list[InsightDashboardFocusItem] = Field(default_factory=list)
    latest_items: list[InsightIntelligenceListItem] = Field(default_factory=list)
