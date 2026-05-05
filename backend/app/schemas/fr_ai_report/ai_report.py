from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.fr_ai_report.report_dsl import FieldRole, FieldType, ReportDSL


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


class ExcelAnalysisResult(BaseModel):
    fileName: str | None = None
    sheets: list[ExcelSheetAnalysis] = Field(default_factory=list)
    primarySheet: str | None = None


class GenerateReportResponse(BaseModel):
    taskId: str
    status: str
    reportName: str
    reportType: str
    previewUrl: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


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


class ReportTaskRead(BaseModel):
    taskId: str
    status: str
    reportName: str
    reportType: str | None = None
    dataSourceStatus: str | None = None
    cptObjectPath: str | None = None
    dslObjectPath: str | None = None
    previewUrl: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    excelAnalysis: ExcelAnalysisResult | None = None
    reportDsl: ReportDSL | None = None
    sqlValidation: SqlValidationResult | None = None
    requirementSummary: dict[str, Any] | None = None
    createTime: datetime
    updateTime: datetime
