from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FrReportCaseSampleBuildRequest(BaseModel):
    sourcePrefix: str = "webroot/APP/reportlets/数据分析"
    sampleMin: int = Field(default=50, ge=1, le=500)
    sampleMax: int = Field(default=100, ge=1, le=500)
    includeScreenshot: bool = True
    previewSuccessOnly: bool = False
    useModelAnalysis: bool = True


class FrReportCaseSampleJobRead(BaseModel):
    jobId: str
    sourcePrefix: str
    sampleMin: int
    sampleMax: int
    includeScreenshot: bool
    previewSuccessOnly: bool
    useModelAnalysis: bool
    status: str
    totalScanned: int
    selectedCount: int
    analyzedCount: int
    candidateCount: int
    caseCount: int
    failedCount: int
    currentObjectPath: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    selectedReports: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    createTime: datetime | None = None
    updateTime: datetime | None = None


class FrReportCaseSearchRequest(BaseModel):
    query: str = ""
    tags: list[str] = Field(default_factory=list)
    sourceObjectPath: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
    includeInactive: bool = False


class FrReportCaseChunkRead(BaseModel):
    chunkId: str
    caseId: str
    sourceObjectPath: str
    chunkType: str
    title: str
    selector: str | None = None
    content: str
    rawXml: str | None = None
    tags: list[str] = Field(default_factory=list)
    searchText: str = ""
    status: str


class FrReportCaseRead(BaseModel):
    caseId: str
    sampleJobId: str | None = None
    sourceObjectPath: str
    reportPath: str | None = None
    reportName: str
    title: str
    scenario: str | None = None
    reason: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    structureSummary: dict[str, Any] = Field(default_factory=dict)
    snippetRefs: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    searchText: str = ""
    qualityScore: float = 0
    previewUrl: str | None = None
    previewStatus: str | None = None
    screenshotObjectPath: str | None = None
    status: str
    createTime: datetime | None = None
    updateTime: datetime | None = None
    chunks: list[FrReportCaseChunkRead] = Field(default_factory=list)


class FrReportCaseSearchHit(BaseModel):
    case: FrReportCaseRead
    score: float
    matchReason: str


class FrReportCaseSearchResponse(BaseModel):
    query: str
    hits: list[FrReportCaseSearchHit] = Field(default_factory=list)
    generationMode: str

