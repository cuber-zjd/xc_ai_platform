from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.agent.fr_report.report_ai_operation import FrReportAiOperationDraftResponse
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
    createTableSql: str | None = None
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


class GenerateCptStepResponse(BaseModel):
    taskId: str
    conversationId: str | None = None
    parentTaskId: str | None = None
    revisionNo: int = 1
    status: str
    reportName: str
    reportType: str
    cptObjectPath: str | None = None
    dslObjectPath: str | None = None
    sqlObjectPath: str | None = None
    createSqlObjectPath: str | None = None
    logObjectPath: str | None = None
    previewUrl: str | None = None
    reportId: str | None = None
    fileVersionId: str | None = None
    structureVersionId: str | None = None
    conflict: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    createTime: datetime
    updateTime: datetime


class FrAiReportAgentContext(BaseModel):
    reportName: str | None = None
    targetFolder: str | None = None
    targetObjectPath: str | None = None
    currentObjectPath: str | None = None
    selectedCell: str | None = None
    selectedDataset: str | None = None
    previewColumns: list[str] = Field(default_factory=list)
    previewRows: list[dict[str, Any]] = Field(default_factory=list)
    sourceTableName: str | None = None
    templateObjectPath: str | None = None
    taskId: str | None = None
    conversationId: str | None = None
    requirement: str | None = None
    ddlDialect: str = "sqlserver"
    idAutoIncrement: bool = True
    activeSkillIds: list[str] = Field(default_factory=list)
    skillInstruction: str | None = None
    allowedToolNames: list[str] = Field(default_factory=list)


class FrAiReportAgentToolRead(BaseModel):
    name: str
    label: str
    category: str
    riskLevel: str = "low"
    autoExecutable: bool = True
    requiresApproval: bool = False
    description: str
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    outputSchema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class FrAiReportAgentSkillRead(BaseModel):
    skillId: str
    name: str
    scope: str = "system"
    enabled: bool = True
    priority: int = 100
    description: str | None = None
    instruction: str
    appliesTo: list[str] = Field(default_factory=list)
    tokenBudget: int = 800


class FrAiReportAgentRuntimePolicy(BaseModel):
    strategy: str = "react"
    maxToolSteps: int = 6
    contextTokenBudget: int = 12000
    autoRunReadOnlyTools: bool = True
    autoCreateDraft: bool = True
    requireApprovalForWrite: bool = True
    memoryPolicy: str = "短期上下文只保留最近对话和工具观察；长期记忆沉淀到任务、反馈和技能配置，进入模型前做摘要压缩。"


class FrAiReportAgentCapabilitiesResponse(BaseModel):
    strategy: FrAiReportAgentRuntimePolicy = Field(default_factory=FrAiReportAgentRuntimePolicy)
    tools: list[FrAiReportAgentToolRead] = Field(default_factory=list)
    skills: list[FrAiReportAgentSkillRead] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)


class FrAiReportAgentEvent(BaseModel):
    type: str
    content: str | None = None
    toolName: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class FrAiReportAgentChatResponse(BaseModel):
    status: str
    conversationId: str | None = None
    taskId: str | None = None
    assistantMessage: str | None = None
    context: FrAiReportAgentContext
    events: list[FrAiReportAgentEvent] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    review: "FrAiReportRequirementReviewResponse | None" = None
    sqlStep: GenerateSqlStepResponse | None = None
    dslStep: GenerateDslStepResponse | None = None
    cptStep: GenerateCptStepResponse | None = None
    operationDraft: FrReportAiOperationDraftResponse | None = None
    capabilities: FrAiReportAgentCapabilitiesResponse | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PreviewValidationResult(BaseModel):
    previewUrl: str
    httpStatus: int | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FrAiReportMaintenanceField(BaseModel):
    name: str
    label: str
    type: str = "string"
    required: bool = True
    description: str | None = None


class FrAiReportMaintenanceTable(BaseModel):
    tableName: str
    displayName: str
    purpose: str
    fields: list[FrAiReportMaintenanceField] = Field(default_factory=list)
    keys: list[str] = Field(default_factory=list)
    uniqueKeys: list[list[str]] = Field(default_factory=list)
    dropdownTargets: list[str] = Field(default_factory=list)


class FrAiReportQualityGate(BaseModel):
    code: str
    label: str
    severity: str = "warning"
    description: str
    autoCheck: bool = False


class FrAiReportWriteBackPlan(BaseModel):
    enabled: bool = False
    mode: str = "none"
    targetTable: str | None = None
    primaryKeys: list[str] = Field(default_factory=list)
    hiddenKeys: list[str] = Field(default_factory=list)
    editableFields: list[str] = Field(default_factory=list)
    readonlyFields: list[str] = Field(default_factory=list)
    calculatedFields: list[str] = Field(default_factory=list)
    allowInsert: bool = False
    allowDelete: bool = False
    widgetPolicy: str = "轻量控件优先；单元格不绑定大数据集下拉，避免填报预览卡顿。"
    safetyNotes: list[str] = Field(default_factory=list)


class FrAiReportRequirementReviewResponse(BaseModel):
    status: str
    scenario: str | None = None
    summary: str
    reportType: str = "detail_table"
    extractedRequirements: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    maintenanceTables: list[FrAiReportMaintenanceTable] = Field(default_factory=list)
    recommendedSourceTables: list[str] = Field(default_factory=list)
    qualityGates: list[FrAiReportQualityGate] = Field(default_factory=list)
    writeBackPlan: FrAiReportWriteBackPlan = Field(default_factory=FrAiReportWriteBackPlan)
    warnings: list[str] = Field(default_factory=list)
    excelAnalysis: ExcelAnalysisResult | None = None


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
