from typing import Any, Literal

from pydantic import BaseModel, Field


class FrReportAiOperationRequest(BaseModel):
    objectPath: str
    prompt: str
    selectedCell: str | None = None
    selectedDataset: str | None = None
    previewColumns: list[str] = Field(default_factory=list)
    previewRows: list[dict[str, Any]] = Field(default_factory=list)
    mode: Literal["modify", "new_report"] = "modify"


class FrReportAiOperationRead(BaseModel):
    operationType: str
    target: str | None = None
    summary: str
    riskLevel: Literal["low", "medium", "high"] = "low"
    payload: dict[str, Any] = Field(default_factory=dict)


class FrReportAiOperationDraftResponse(BaseModel):
    draftId: str
    baseVersion: str
    targetVersion: str
    status: Literal["draft", "blocked"]
    assistantMessage: str
    operations: list[FrReportAiOperationRead] = Field(default_factory=list)
    previewPatch: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    modelName: str | None = None
    warnings: list[str] = Field(default_factory=list)


class FrReportAiUploadedFileRead(BaseModel):
    fileName: str
    contentType: str | None = None
    size: int = 0
    textPreview: str | None = None


class FrReportAiNewReportPlanResponse(BaseModel):
    draftId: str
    status: Literal["proposal", "blocked"]
    assistantMessage: str
    questions: list[str] = Field(default_factory=list)
    proposal: dict[str, Any] = Field(default_factory=dict)
    operations: list[FrReportAiOperationRead] = Field(default_factory=list)
    templateSummary: dict[str, Any] = Field(default_factory=dict)
    uploadedFiles: list[FrReportAiUploadedFileRead] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class FrReportAiApplyDraftRequest(BaseModel):
    objectPath: str
    draftId: str
    prompt: str | None = None
    selectedCell: str | None = None
    selectedDataset: str | None = None
    assistantMessage: str
    operations: list[FrReportAiOperationRead] = Field(default_factory=list)
    previewPatch: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class FrReportSnapshotRead(BaseModel):
    snapshotId: str
    objectPath: str
    reportPath: str | None = None
    fileName: str | None = None
    parentSnapshotId: str | None = None
    snapshotNo: int
    status: str
    title: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    appliedPatch: dict[str, Any] = Field(default_factory=dict)


class FrReportAiApplyDraftResponse(BaseModel):
    draftId: str
    status: Literal["applied", "blocked"]
    baseSnapshot: FrReportSnapshotRead
    targetSnapshot: FrReportSnapshotRead
    targetVersion: str
    assistantMessage: str
    operations: list[FrReportAiOperationRead] = Field(default_factory=list)
    previewPatch: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class FrReportAiSnapshotCptRequest(BaseModel):
    snapshotId: str


class FrReportAiSnapshotCptResponse(BaseModel):
    snapshotId: str
    status: Literal["generated", "preview_failed"]
    cptObjectPath: str
    metaObjectPath: str | None = None
    operationsObjectPath: str | None = None
    logObjectPath: str | None = None
    previewUrl: str
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
