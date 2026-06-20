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
    reportName: str | None = None
    targetFolder: str | None = None
    targetObjectPath: str | None = None
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
    reportName: str | None = None
    targetFolder: str | None = None
    targetObjectPath: str | None = None
    conflictStrategy: Literal["abort", "archive_and_overwrite", "import_external"] = "abort"


class FrReportAiSnapshotCptResponse(BaseModel):
    snapshotId: str
    status: Literal["generated", "preview_failed", "conflict"]
    cptObjectPath: str
    metaObjectPath: str | None = None
    operationsObjectPath: str | None = None
    logObjectPath: str | None = None
    previewUrl: str
    reportId: str | None = None
    fileVersionId: str | None = None
    structureVersionId: str | None = None
    conflict: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class FrReportProjectRead(BaseModel):
    reportId: str
    reportName: str
    reportCode: str
    targetFolder: str
    currentObjectPath: str
    currentStructureVersionId: str | None = None
    currentFileVersionId: str | None = None
    status: str


class FrReportStructureVersionRead(BaseModel):
    structureVersionId: str
    reportId: str
    snapshotId: str | None = None
    versionNo: int
    versionName: str | None = None
    parentVersionId: str | None = None
    sourceType: str
    status: str
    createTime: str
    diffSummary: dict[str, Any] = Field(default_factory=dict)


class FrReportFileVersionRead(BaseModel):
    fileVersionId: str
    reportId: str
    structureVersionId: str | None = None
    versionNo: int
    versionName: str | None = None
    currentObjectPath: str
    archiveObjectPath: str
    manifestObjectPath: str | None = None
    sourceFileHash: str | None = None
    targetFileHash: str | None = None
    sourceLastModified: str | None = None
    targetLastModified: str | None = None
    writeStatus: str
    previewUrl: str | None = None
    createTime: str
    diffSummary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class FrReportVersionListResponse(BaseModel):
    project: FrReportProjectRead | None = None
    structureVersions: list[FrReportStructureVersionRead] = Field(default_factory=list)
    fileVersions: list[FrReportFileVersionRead] = Field(default_factory=list)
    externalConflict: dict[str, Any] | None = None


class FrReportVersionRollbackRequest(BaseModel):
    fileVersionId: str


class FrReportVersionRollbackResponse(BaseModel):
    reportId: str
    restoredFileVersionId: str
    newFileVersionId: str
    currentObjectPath: str
    previewUrl: str | None = None
    warnings: list[str] = Field(default_factory=list)


class FrReportStructureRollbackRequest(BaseModel):
    structureVersionId: str


class FrReportStructureRollbackResponse(BaseModel):
    reportId: str
    restoredStructureVersionId: str
    newStructureVersionId: str
    currentObjectPath: str
    warnings: list[str] = Field(default_factory=list)


class FrReportExternalSyncRequest(BaseModel):
    objectPath: str


class FrReportExternalSyncResponse(BaseModel):
    reportId: str
    fileVersion: FrReportFileVersionRead
    currentObjectPath: str
    warnings: list[str] = Field(default_factory=list)


class FrReportRecycleRequest(BaseModel):
    objectPath: str


class FrReportRecycleResponse(BaseModel):
    reportId: str
    recycledObjectPath: str
    trashObjectPath: str
    warnings: list[str] = Field(default_factory=list)
