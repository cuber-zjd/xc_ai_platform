from pydantic import BaseModel, Field


class InsightQualityMetric(BaseModel):
    key: str
    label: str
    value: float
    unit: str = ""
    description: str | None = None


class InsightQualityReason(BaseModel):
    reason: str
    count: int
    category: str = "unknown"
    raw_reason: str | None = None
    suggestion: str | None = None


class InsightQualitySourceMetric(BaseModel):
    data_source_id: int | None = None
    data_source_name: str
    total_tasks: int
    success_tasks: int
    failed_tasks: int
    success_rate: float


class InsightQualityOverview(BaseModel):
    collection_metrics: list[InsightQualityMetric] = Field(default_factory=list)
    review_metrics: list[InsightQualityMetric] = Field(default_factory=list)
    ai_metrics: list[InsightQualityMetric] = Field(default_factory=list)
    failure_reasons: list[InsightQualityReason] = Field(default_factory=list)
    source_metrics: list[InsightQualitySourceMetric] = Field(default_factory=list)
    generated_at: str
