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
}

export interface ReportDslDataset {
    name: string;
    sql: string;
    fields: ReportDslField[];
}

export interface ReportDsl {
    schemaVersion: string;
    reportName: string;
    reportType: ReportType;
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
    status: string;
    reportName: string;
    reportType: ReportType | string;
    previewUrl?: string | null;
    warnings: string[];
    errors: string[];
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
    status: string;
    reportName: string;
    reportType?: string | null;
    dataSourceStatus?: string | null;
    cptObjectPath?: string | null;
    dslObjectPath?: string | null;
    previewUrl?: string | null;
    errors: string[];
    warnings: string[];
    excelAnalysis?: ExcelAnalysisResult | null;
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
}
