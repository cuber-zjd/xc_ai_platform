from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.fr_report.report_dsl import FieldRole, FieldType, ReportDSL


class ExcelFieldAnalysis(BaseModel):
    name: str
    label: str
    type: FieldType
    role: FieldRole
    sampleValues: list[Any] = Field(default_factory=list)
    nullRate: float = 0


class ExcelSheetAnalysis(BaseModel):
    sheetName: str
    headerRowIndex: int
    rowCount: int
    fields: list[ExcelFieldAnalysis]
    sampleRows: list[dict[str, Any]] = Field(default_factory=list)
    templateAnalysis: dict[str, Any] | None = None


class ExcelAnalysisResult(BaseModel):
    fileName: str | None = None
    sheets: list[ExcelSheetAnalysis] = Field(default_factory=list)
    primarySheet: str | None = None


class GenerateReportResponse(BaseModel):
    taskId: str
    conversationId: str | None = None
    status: str
    reportName: str
    reportType: str
    previewUrl: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class GenerateSqlStepResponse(BaseModel):
    taskId: str
    conversationId: str | None = None
    parentTaskId: str | None = None
    revisionNo: int = 1
    status: str
    reportName: str
    reportType: str
    dataSourceStatus: str | None = None
    sourceTableName: str | None = None
    sourceFileName: str | None = None
    requirementText: str | None = None
    requirementSummary: dict[str, Any] | None = None
    excelAnalysis: ExcelAnalysisResult | None = None
    querySql: str | None = None
    sqlValidation: "SqlValidationResult | None" = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    createTime: datetime
    updateTime: datetime


class GenerateDslStepResponse(BaseModel):
    taskId: str
    conversationId: str | None = None
    parentTaskId: str | None = None
    revisionNo: int = 1
    status: str
    reportName: str
    reportType: str
    reportDsl: ReportDSL | None = None
    sqlValidation: "SqlValidationResult | None" = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    createTime: datetime
    updateTime: datetime


class PreviewValidationResult(BaseModel):
    previewUrl: str
    httpStatus: int | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SqlValidationResult(BaseModel):
    enabled: bool = False
    configured: bool = False
    success: bool = False
    executed: bool = False
    rowCount: int | None = None
    columns: list[str] = Field(default_factory=list)
    sampleRows: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CptPublishResponse(BaseModel):
    taskId: str
    status: str
    cptObjectPath: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ReportTaskListItem(BaseModel):
    taskId: str
    conversationId: str | None = None
    parentTaskId: str | None = None
    revisionNo: int = 1
    status: str
    reportName: str
    reportType: str | None = None
    dataSourceStatus: str | None = None
    sourceTableName: str | None = None
    sourceFileName: str | None = None
    requirementText: str | None = None
    previewUrl: str | None = None
    errorCount: int = 0
    warningCount: int = 0
    createTime: datetime
    updateTime: datetime


class FrAiReportConversationRead(BaseModel):
    conversationId: str
    title: str
    userId: str | None = None
    latestTaskId: str | None = None
    status: str
    sourceTableName: str | None = None
    summary: dict[str, Any] | None = None
    createTime: datetime
    updateTime: datetime


class FrAiReportFeedbackCreate(BaseModel):
    feedbackType: str = Field(default="note")
    content: str
    payload: dict[str, Any] | None = None
    isPositive: bool | None = None


class FrAiReportFeedbackRead(BaseModel):
    feedbackId: str
    conversationId: str | None = None
    taskId: str
    feedbackType: str
    content: str
    payload: dict[str, Any] | None = None
    isPositive: bool | None = None
    createTime: datetime
    updateTime: datetime


class ReportTaskRead(BaseModel):
    taskId: str
    conversationId: str | None = None
    parentTaskId: str | None = None
    revisionNo: int = 1
    status: str
    reportName: str
    reportType: str | None = None
    dataSourceStatus: str | None = None
    sourceTableName: str | None = None
    sourceFileName: str | None = None
    requirementText: str | None = None
    cptObjectPath: str | None = None
    dslObjectPath: str | None = None
    previewUrl: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    excelAnalysis: ExcelAnalysisResult | None = None
    querySql: str | None = None
    reportDsl: ReportDSL | None = None
    sqlValidation: SqlValidationResult | None = None
    requirementSummary: dict[str, Any] | None = None
    createTime: datetime
    updateTime: datetime
