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
    hidden?: boolean;
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
    writeBack?: {
        enabled: boolean;
        submitterName: string;
        databaseName?: string | null;
        schemaName: string;
        tableName?: string | null;
        mode: string;
        toolbar: boolean;
        rowActions: {
            enabled: boolean;
            insertLabel: string;
            deleteLabel: string;
            columnWidth: number;
        };
        widgets: Array<Record<string, unknown>>;
        columns: Array<Record<string, unknown>>;
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
    createTableSql?: string | null;
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

export interface GenerateCptStepResponse {
    taskId: string;
    conversationId?: string | null;
    parentTaskId?: string | null;
    revisionNo: number;
    status: string;
    reportName: string;
    reportType: ReportType | string;
    cptObjectPath?: string | null;
    dslObjectPath?: string | null;
    sqlObjectPath?: string | null;
    createSqlObjectPath?: string | null;
    logObjectPath?: string | null;
    previewUrl?: string | null;
    reportId?: string | null;
    fileVersionId?: string | null;
    structureVersionId?: string | null;
    conflict?: Record<string, unknown> | null;
    warnings: string[];
    errors: string[];
    createTime: string;
    updateTime: string;
}

export interface GenerateCptStepPayload {
    taskId: string;
    reportName?: string | null;
    targetFolder?: string | null;
    targetObjectPath?: string | null;
    conflictStrategy?: 'abort' | 'archive_and_overwrite' | 'import_external';
}

export interface FrAiReportAgentContext {
    reportName?: string | null;
    targetFolder?: string | null;
    targetObjectPath?: string | null;
    sourceTableName?: string | null;
    templateObjectPath?: string | null;
    taskId?: string | null;
    conversationId?: string | null;
    requirement?: string | null;
    ddlDialect?: 'sqlserver' | 'mysql' | 'postgresql' | string;
    idAutoIncrement?: boolean;
}

export type FrAiReportAgentAction = 'chat' | 'start_generate' | 'save_cpt';

export interface FrAiReportAgentChatPayload {
    message: string;
    action?: FrAiReportAgentAction;
    context?: FrAiReportAgentContext;
    file?: File | null;
}

export interface FrAiReportAgentEvent {
    type: string;
    content?: string | null;
    toolName?: string | null;
    payload: Record<string, unknown>;
}

export interface FrAiReportAgentChatResponse {
    status: string;
    conversationId?: string | null;
    taskId?: string | null;
    context: FrAiReportAgentContext;
    events: FrAiReportAgentEvent[];
    questions: string[];
    review?: FrAiReportRequirementReviewResponse | null;
    sqlStep?: GenerateSqlStepResponse | null;
    dslStep?: GenerateDslStepResponse | null;
    cptStep?: GenerateCptStepResponse | null;
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
    sqlObjectPath?: string | null;
    createSqlObjectPath?: string | null;
    logObjectPath?: string | null;
    previewUrl?: string | null;
    errors: string[];
    warnings: string[];
    excelAnalysis?: ExcelAnalysisResult | null;
    querySql?: string | null;
    createTableSql?: string | null;
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
    ddlDialect?: 'sqlserver' | 'mysql' | 'postgresql';
    idAutoIncrement?: boolean;
    tableNameOverridesJson?: string;
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

export interface FrReportFileRead {
    objectPath: string;
    reportPath: string;
    fileName: string;
    fileType: string;
    size?: number | null;
    etag?: string | null;
    lastModified?: string | null;
}

export interface FrReportFileListResponse {
    bucket: string;
    prefix: string;
    allowedPrefixes: string[];
    extensions: string[];
    total: number;
    items: FrReportFileRead[];
    visibleOnly: boolean;
    selectedVisiblePaths: string[];
}

export interface FrReportVisibilityPreferenceRead {
    visiblePaths: string[];
}

export interface FrReportVisibilityPreferencePayload {
    visiblePaths: string[];
}

export interface FrReportDatasetParameterRead {
    name: string;
    defaultValue?: string | null;
}

export interface FrReportDatasetRead {
    name: string;
    className?: string | null;
    databaseName?: string | null;
    parameters: FrReportDatasetParameterRead[];
    querySql?: string | null;
    querySqlTruncated: boolean;
}

export interface FrReportStructureSummaryRead {
    datasetCount: number;
    parameterCount: number;
    widgetCount: number;
    queryCount: number;
    sheetCount: number;
    cellCount: number;
    mergeCount: number;
}

export interface FrReportCellStyleRead {
    styleName?: string | null;
    fontFamily?: string | null;
    fontSize?: number | null;
    bold?: boolean | null;
    italic?: boolean | null;
    underline?: boolean | null;
    color?: string | null;
    backgroundColor?: string | null;
    borderColor?: string | null;
    borderTop?: boolean | null;
    borderRight?: boolean | null;
    borderBottom?: boolean | null;
    borderLeft?: boolean | null;
    horizontalAlign?: string | null;
    verticalAlign?: string | null;
}

export interface FrReportFieldBindingRead {
    dataset?: string | null;
    field?: string | null;
    expression: string;
    aggregation?: string | null;
}

export interface FrReportConditionRead {
    column?: string | null;
    operator?: string | null;
    value?: string | null;
    join?: string | null;
}

export interface FrReportDataColumnRead {
    dataset?: string | null;
    field?: string | null;
    parentCell?: string | null;
    aggregation?: string | null;
    expandDirection?: string | null;
    customDisplay?: string | null;
    horizontalExtendable?: boolean | null;
    verticalExtendable?: boolean | null;
    conditions: FrReportConditionRead[];
}

export interface FrReportCellWidgetRead {
    widgetClass?: string | null;
    widgetType?: string | null;
    widgetName?: string | null;
    description?: string | null;
}

export interface FrReportSubmitColumnRead {
    column: string;
    value?: string | null;
    isKey: boolean;
    skipUnmodified: boolean;
    cell?: string | null;
}

export interface FrReportSubmitBindingRead {
    name?: string | null;
    database?: string | null;
    schemaName?: string | null;
    tableName?: string | null;
    submitterClass?: string | null;
    columns: FrReportSubmitColumnRead[];
}

export interface FrReportCellRead {
    row: number;
    column: number;
    address: string;
    text?: string | null;
    formula?: string | null;
    fieldBinding?: FrReportFieldBindingRead | null;
    dataColumn?: FrReportDataColumnRead | null;
    widget?: FrReportCellWidgetRead | null;
    submitBindings: FrReportSubmitBindingRead[];
    rowSpan: number;
    colSpan: number;
    expandDirection?: string | null;
    style: FrReportCellStyleRead;
    rawTag?: string | null;
    rawPath?: string | null;
}

export interface FrReportMergeRead {
    startRow: number;
    startColumn: number;
    endRow: number;
    endColumn: number;
}

export interface FrReportDimensionRead {
    index: number;
    size?: number | null;
}

export interface FrReportSheetRead {
    name: string;
    rowCount: number;
    columnCount: number;
    rows: FrReportDimensionRead[];
    columns: FrReportDimensionRead[];
    cells: FrReportCellRead[];
    merges: FrReportMergeRead[];
    submitBindings: FrReportSubmitBindingRead[];
    warnings: string[];
}

export interface FrReportDocumentRead {
    title?: string | null;
    sheets: FrReportSheetRead[];
    unsupportedNodes: string[];
    parseCoverage: Record<string, number>;
}

export interface FrReportFileStructureRead {
    objectPath: string;
    reportPath: string;
    fileName: string;
    fileType: string;
    size?: number | null;
    etag?: string | null;
    lastModified?: string | null;
    format: string;
    encoding?: string | null;
    xmlVersion?: string | null;
    releaseVersion?: string | null;
    rootTag?: string | null;
    datasets: FrReportDatasetRead[];
    document?: FrReportDocumentRead | null;
    summary: FrReportStructureSummaryRead;
    warnings: string[];
}

export interface FrReportDatabaseConnectionRead {
    connectionName: string;
    driverKey: string;
    driverName?: string | null;
    dbType: string;
    host: string;
    port: number;
    database: string;
    username: string;
    odbcDriver?: string | null;
    configured: boolean;
}

export interface FrReportDatabaseConnectionPayload {
    connectionName: string;
    driverKey: string;
    dbType?: string;
    host: string;
    port: number;
    database: string;
    username: string;
    password: string;
    odbcDriver?: string | null;
}

export interface FrReportDatabaseDriverRead {
    driverKey: string;
    displayName: string;
    dbType: string;
    pythonDriver: string;
    odbcDriver?: string | null;
    defaultPort: number;
    description?: string | null;
}

export interface FrReportAiOperationPayload {
    objectPath: string;
    prompt: string;
    selectedCell?: string | null;
    selectedDataset?: string | null;
    previewColumns: string[];
    previewRows?: Record<string, unknown>[];
    mode?: 'modify' | 'new_report';
}

export interface FrReportAiOperationRead {
    operationType: string;
    target?: string | null;
    summary: string;
    riskLevel: 'low' | 'medium' | 'high';
    payload: Record<string, unknown>;
}

export interface FrReportAiOperationDraftResponse {
    draftId: string;
    baseVersion: string;
    targetVersion: string;
    status: 'draft' | 'blocked';
    assistantMessage: string;
    operations: FrReportAiOperationRead[];
    previewPatch: Record<string, unknown>;
    safety: Record<string, unknown>;
    modelName?: string | null;
    warnings: string[];
}

export interface FrReportAiUploadedFileRead {
    fileName: string;
    contentType?: string | null;
    size: number;
    textPreview?: string | null;
}

export interface FrReportAiNewReportPlanPayload {
    requirement: string;
    templateObjectPath?: string | null;
    reportName?: string | null;
    targetFolder?: string | null;
    files?: File[];
}

export interface FrReportAiNewReportPlanResponse {
    draftId: string;
    status: 'proposal' | 'blocked';
    assistantMessage: string;
    reportName?: string | null;
    targetFolder?: string | null;
    targetObjectPath?: string | null;
    questions: string[];
    proposal: Record<string, unknown>;
    operations: FrReportAiOperationRead[];
    templateSummary: Record<string, unknown>;
    uploadedFiles: FrReportAiUploadedFileRead[];
    safety: Record<string, unknown>;
    warnings: string[];
}

export interface FrAiReportRequirementReviewPayload {
    requirement?: string | null;
    sourceTableName?: string | null;
    tableSchemaJson?: string | null;
    file?: File | null;
}

export interface FrAiReportMaintenanceField {
    name: string;
    label: string;
    type: string;
    required: boolean;
    description?: string | null;
}

export interface FrAiReportMaintenanceTable {
    tableName: string;
    displayName: string;
    purpose: string;
    fields: FrAiReportMaintenanceField[];
    keys: string[];
    uniqueKeys: string[][];
    dropdownTargets: string[];
}

export interface FrAiReportQualityGate {
    code: string;
    label: string;
    severity: string;
    description: string;
    autoCheck: boolean;
}

export interface FrAiReportWriteBackPlan {
    enabled: boolean;
    mode: string;
    targetTable?: string | null;
    primaryKeys: string[];
    hiddenKeys: string[];
    editableFields: string[];
    readonlyFields: string[];
    calculatedFields: string[];
    allowInsert: boolean;
    allowDelete: boolean;
    widgetPolicy: string;
    safetyNotes: string[];
}

export interface FrAiReportRequirementReviewResponse {
    status: string;
    scenario?: string | null;
    summary: string;
    reportType: string;
    extractedRequirements: string[];
    questions: string[];
    assumptions: string[];
    maintenanceTables: FrAiReportMaintenanceTable[];
    recommendedSourceTables: string[];
    qualityGates: FrAiReportQualityGate[];
    writeBackPlan: FrAiReportWriteBackPlan;
    warnings: string[];
    excelAnalysis?: ExcelAnalysisResult | null;
}

export interface FrReportAiApplyDraftPayload {
    objectPath: string;
    draftId: string;
    prompt?: string | null;
    selectedCell?: string | null;
    selectedDataset?: string | null;
    assistantMessage: string;
    operations: FrReportAiOperationRead[];
    previewPatch: Record<string, unknown>;
    safety: Record<string, unknown>;
    warnings: string[];
}

export interface FrReportSnapshotRead {
    snapshotId: string;
    objectPath: string;
    reportPath?: string | null;
    fileName?: string | null;
    parentSnapshotId?: string | null;
    snapshotNo: number;
    status: string;
    title?: string | null;
    summary: Record<string, unknown>;
    appliedPatch: Record<string, unknown>;
}

export interface FrReportAiApplyDraftResponse {
    draftId: string;
    status: 'applied' | 'blocked';
    baseSnapshot: FrReportSnapshotRead;
    targetSnapshot: FrReportSnapshotRead;
    targetVersion: string;
    assistantMessage: string;
    operations: FrReportAiOperationRead[];
    previewPatch: Record<string, unknown>;
    warnings: string[];
}

export interface FrReportAiSnapshotCptPayload {
    snapshotId: string;
    reportName?: string | null;
    targetFolder?: string | null;
    targetObjectPath?: string | null;
    conflictStrategy?: 'abort' | 'archive_and_overwrite' | 'import_external';
}

export interface FrReportAiSnapshotCptResponse {
    snapshotId: string;
    status: 'generated' | 'preview_failed' | 'conflict';
    cptObjectPath: string;
    metaObjectPath?: string | null;
    operationsObjectPath?: string | null;
    logObjectPath?: string | null;
    previewUrl: string;
    reportId?: string | null;
    fileVersionId?: string | null;
    structureVersionId?: string | null;
    conflict?: Record<string, unknown> | null;
    warnings: string[];
    errors: string[];
}

export interface FrReportProjectRead {
    reportId: string;
    reportName: string;
    reportCode: string;
    targetFolder: string;
    currentObjectPath: string;
    currentStructureVersionId?: string | null;
    currentFileVersionId?: string | null;
    status: string;
}

export interface FrReportStructureVersionRead {
    structureVersionId: string;
    reportId: string;
    snapshotId?: string | null;
    versionNo: number;
    versionName?: string | null;
    parentVersionId?: string | null;
    sourceType: string;
    status: string;
    createTime: string;
    diffSummary: Record<string, unknown>;
}

export interface FrReportFileVersionRead {
    fileVersionId: string;
    reportId: string;
    structureVersionId?: string | null;
    versionNo: number;
    versionName?: string | null;
    currentObjectPath: string;
    archiveObjectPath: string;
    manifestObjectPath?: string | null;
    sourceFileHash?: string | null;
    targetFileHash?: string | null;
    sourceLastModified?: string | null;
    targetLastModified?: string | null;
    writeStatus: string;
    previewUrl?: string | null;
    createTime: string;
    diffSummary: Record<string, unknown>;
    warnings: string[];
    errors: string[];
}

export interface FrReportVersionListResponse {
    project?: FrReportProjectRead | null;
    structureVersions: FrReportStructureVersionRead[];
    fileVersions: FrReportFileVersionRead[];
    externalConflict?: Record<string, unknown> | null;
}

export interface FrReportVersionRollbackResponse {
    reportId: string;
    restoredFileVersionId: string;
    newFileVersionId: string;
    currentObjectPath: string;
    previewUrl?: string | null;
    warnings: string[];
}

export interface FrReportStructureRollbackResponse {
    reportId: string;
    restoredStructureVersionId: string;
    newStructureVersionId: string;
    currentObjectPath: string;
    warnings: string[];
}

export interface FrReportExternalSyncResponse {
    reportId: string;
    fileVersion: FrReportFileVersionRead;
    currentObjectPath: string;
    warnings: string[];
}

export interface FrReportRecycleResponse {
    reportId: string;
    recycledObjectPath: string;
    trashObjectPath: string;
    warnings: string[];
}

export interface FrReportDatasetPreviewParameter {
    name: string;
    value?: string | number | boolean | null;
}

export interface FrReportDatasetPreviewPayload {
    connectionName: string;
    querySql: string;
    parameters: FrReportDatasetPreviewParameter[];
    maxRows?: number;
}

export interface FrReportDatasetPreviewResponse {
    connectionName: string;
    needsConnection: boolean;
    executed: boolean;
    success: boolean;
    columns: string[];
    sampleRows: Record<string, unknown>[];
    rowCount: number;
    errors: string[];
    warnings: string[];
}
