from pydantic import BaseModel, Field


class InsightOperationMetric(BaseModel):
    key: str
    label: str
    value: float | int | str | None = None
    unit: str | None = None
    trend: str | None = None
    description: str | None = None
    severity: str = "normal"


class InsightOperationEvidence(BaseModel):
    title: str
    reportPath: str
    tables: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    note: str | None = None


class InsightOperationSignal(BaseModel):
    title: str
    level: str
    domain: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    suggestion: str


class InsightOperationSeriesPoint(BaseModel):
    label: str
    value: float | int
    extra: dict[str, object | None] = Field(default_factory=dict)


class InsightOperationTableRow(BaseModel):
    name: str
    values: dict[str, object | None] = Field(default_factory=dict)


class InsightOperationDomain(BaseModel):
    key: str
    title: str
    subtitle: str | None = None
    score: int | None = None
    scoreLabel: str | None = None
    metrics: list[InsightOperationMetric] = Field(default_factory=list)
    series: list[InsightOperationSeriesPoint] = Field(default_factory=list)
    rows: list[InsightOperationTableRow] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    evidenceReports: list[str] = Field(default_factory=list)


class InsightOperationLifecycleSection(BaseModel):
    key: str
    title: str
    subtitle: str | None = None
    metrics: list[InsightOperationMetric] = Field(default_factory=list)
    rows: list[InsightOperationTableRow] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class InsightOperationCustomerLifecycle(BaseModel):
    generatedAt: str
    companyName: str = "健源公司"
    analysisDate: str | None = None
    analysisPeriod: str | None = None
    headline: str
    summary: list[str] = Field(default_factory=list)
    metrics: list[InsightOperationMetric] = Field(default_factory=list)
    sections: list[InsightOperationLifecycleSection] = Field(default_factory=list)
    signals: list[InsightOperationSignal] = Field(default_factory=list)
    evidence: list[InsightOperationEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InsightOperationOverview(BaseModel):
    generatedAt: str
    companyName: str = "健源公司"
    analysisDate: str | None = None
    analysisPeriod: str | None = None
    dataFreshness: list[str] = Field(default_factory=list)
    headline: str
    executiveSummary: list[str] = Field(default_factory=list)
    kpis: list[InsightOperationMetric] = Field(default_factory=list)
    signals: list[InsightOperationSignal] = Field(default_factory=list)
    domains: list[InsightOperationDomain] = Field(default_factory=list)
    evidence: list[InsightOperationEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
