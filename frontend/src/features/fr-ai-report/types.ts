export type ReportType = 'detail_table' | 'group_table' | 'pivot_table';

export type FieldType = 'string' | 'integer' | 'decimal' | 'date' | 'datetime' | 'boolean';

export type FieldRole = 'dimension' | 'measure' | 'date' | 'text';

export interface ExcelFieldAnalysis {
    name: string;
    label: string;
    type: FieldType;
    role: FieldRole;
    sampleValues: unknown[];
    nullRate: number;
}

export interface ExcelSheetAnalysis {
    sheetName: string;
    headerRowIndex: number;
    rowCount: number;
    fields: ExcelFieldAnalysis[];
    sampleRows: Record<string, unknown>[];
    templateAnalysis?: Record<string, unknown> | null;
}

export interface ExcelAnalysisResult {
    fileName?: string | null;
    sheets: ExcelSheetAnalysis[];
    primarySheet?: string | null;
}

export interface ReportDslField {
    name: string;
    label: string;
    type: FieldType;
    role: FieldRole;
    aggregation?: string;
    sourceTable?: string | null;
    tableAlias?: string | null;
    sourceField?: string | null;
    sourceType?: string | null;
    nullable?: boolean | null;
}

export interface ReportDslParameter {
    name: string;
    label: string;
    type: FieldType;
    required: boolean;
    default?: unknown;
    bindExpression?: string | null;
}

export interface ReportDslColumn {
    field: string;
    title: string;
    width: number;
    type: FieldType;
    role: FieldRole;
    aggregation: string;
    format?: string | null;
    group: boolean;
    expandDirection?: 'down' | 'right' | 'none';
}

export interface ReportDslDataset {
    name: string;
    sql: string;
    fields: ReportDslField[];
}

export interface ReportDslMeta {
    title?: string | null;
    subtitle?: string | null;
    unit?: string | null;
    updateText?: string | null;
    averageLabel?: string | null;
    remarks: string[];
    filters: Array<Record<string, unknown>>;
}

export interface ReportDsl {
    schemaVersion: string;
    reportName: string;
    reportType: ReportType;
    reportMeta?: ReportDslMeta;
    parameters: ReportDslParameter[];
    dataModel: {
        tableName: string;
        dataSourceStatus: 'provided' | 'designed_not_verified';
        fields: ReportDslField[];
        createTableSql?: string | null;
        tables?: Array<Record<string, unknown>>;
        joinHints?: Array<Record<string, string>>;
    };
    datasets: ReportDslDataset[];
    layout: {
        dataset: string;
        columns: ReportDslColumn[];
        rowGroupFields: string[];
        columnGroupFields: string[];
        valueFields: string[];
        horizontalExpansion?: {
            enabled: boolean;
            dimensionField?: string | null;
            valueFields: string[];
            direction: 'right';
            sourceLabels: string[];
        } | null;
        designHints?: Record<string, unknown>;
        chartType?: string | null;
    };
    rules: {
        conditionalFormats: Array<Record<string, unknown>>;
        freezeHeader: boolean;
        showRowNumber: boolean;
        pageSize: number;
    };
}

export interface GenerateReportResponse {
    taskId: string;
    conversationId?: string | null;
    status: string;
    reportName: string;
    reportType: ReportType | string;
    previewUrl?: string | null;
    warnings: string[];
    errors: string[];
}

export interface GenerateSqlStepResponse {
    taskId: string;
    conversationId?: string | null;
    parentTaskId?: string | null;
    revisionNo: number;
    status: string;
    reportName: string;
    reportType: ReportType | string;
    dataSourceStatus?: string | null;
    sourceTableName?: string | null;
    sourceFileName?: string | null;
    requirementText?: string | null;
    requirementSummary?: Record<string, unknown> | null;
    excelAnalysis?: ExcelAnalysisResult | null;
    querySql?: string | null;
    sqlValidation?: SqlValidationResult | null;
    warnings: string[];
    errors: string[];
    createTime: string;
    updateTime: string;
}

export interface GenerateDslStepResponse {
    taskId: string;
    conversationId?: string | null;
    parentTaskId?: string | null;
    revisionNo: number;
    status: string;
    reportName: string;
    reportType: ReportType | string;
    reportDsl?: ReportDsl | null;
    sqlValidation?: SqlValidationResult | null;
    warnings: string[];
    errors: string[];
    createTime: string;
    updateTime: string;
}

export interface PreviewValidationResult {
    previewUrl: string;
    httpStatus?: number | null;
    errors: string[];
    warnings: string[];
}

export interface SqlValidationResult {
    enabled: boolean;
    configured: boolean;
    success: boolean;
    executed: boolean;
    rowCount?: number | null;
    columns: string[];
    sampleRows: Record<string, unknown>[];
    errors: string[];
    warnings: string[];
}

export interface CptPublishResponse {
    taskId: string;
    status: string;
    cptObjectPath?: string | null;
    warnings: string[];
}

export interface ReportTaskRead {
    taskId: string;
    conversationId?: string | null;
    parentTaskId?: string | null;
    revisionNo: number;
    status: string;
    reportName: string;
    reportType?: string | null;
    dataSourceStatus?: string | null;
    sourceTableName?: string | null;
    sourceFileName?: string | null;
    requirementText?: string | null;
    cptObjectPath?: string | null;
    dslObjectPath?: string | null;
    previewUrl?: string | null;
    errors: string[];
    warnings: string[];
    excelAnalysis?: ExcelAnalysisResult | null;
    querySql?: string | null;
    reportDsl?: ReportDsl | null;
    sqlValidation?: SqlValidationResult | null;
    requirementSummary?: Record<string, unknown> | null;
    createTime: string;
    updateTime: string;
}

export interface GenerateReportPayload {
    requirement: string;
    reportName?: string;
    sourceTableName?: string;
    file?: File | null;
    tableSchemaJson?: string;
    conversationId?: string | null;
}

export interface PageResult<T> {
    total: number;
    items: T[];
    page: number;
    size: number;
}

export interface ReportTaskListItem {
    taskId: string;
    conversationId?: string | null;
    parentTaskId?: string | null;
    revisionNo: number;
    status: string;
    reportName: string;
    reportType?: string | null;
    dataSourceStatus?: string | null;
    sourceTableName?: string | null;
    sourceFileName?: string | null;
    requirementText?: string | null;
    previewUrl?: string | null;
    errorCount: number;
    warningCount: number;
    createTime: string;
    updateTime: string;
}

export interface FrAiReportFeedbackPayload {
    feedbackType?: string;
    content: string;
    payload?: Record<string, unknown> | null;
    isPositive?: boolean | null;
}

export interface FrAiReportFeedbackRead {
    feedbackId: string;
    conversationId?: string | null;
    taskId: string;
    feedbackType: string;
    content: string;
    payload?: Record<string, unknown> | null;
    isPositive?: boolean | null;
    createTime: string;
    updateTime: string;
}
