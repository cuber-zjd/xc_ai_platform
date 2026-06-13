from datetime import datetime

from pydantic import BaseModel, Field


class FrReportFileRead(BaseModel):
    objectPath: str
    reportPath: str
    fileName: str
    fileType: str
    size: int | None = None
    etag: str | None = None
    lastModified: datetime | None = None


class FrReportFileListResponse(BaseModel):
    bucket: str
    prefix: str
    allowedPrefixes: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    total: int
    items: list[FrReportFileRead] = Field(default_factory=list)
    visibleOnly: bool = False
    selectedVisiblePaths: list[str] = Field(default_factory=list)


class FrReportVisibilityPreferenceRead(BaseModel):
    visiblePaths: list[str] = Field(default_factory=list)


class FrReportVisibilityPreferenceUpdate(BaseModel):
    visiblePaths: list[str] = Field(default_factory=list)


class FrReportDatasetParameterRead(BaseModel):
    name: str
    defaultValue: str | None = None


class FrReportDatasetRead(BaseModel):
    name: str
    className: str | None = None
    databaseName: str | None = None
    parameters: list[FrReportDatasetParameterRead] = Field(default_factory=list)
    querySql: str | None = None
    querySqlTruncated: bool = False


class FrReportStructureSummaryRead(BaseModel):
    datasetCount: int = 0
    parameterCount: int = 0
    widgetCount: int = 0
    queryCount: int = 0
    sheetCount: int = 0
    cellCount: int = 0
    mergeCount: int = 0


class FrReportCellStyleRead(BaseModel):
    styleName: str | None = None
    fontFamily: str | None = None
    fontSize: int | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: str | None = None
    backgroundColor: str | None = None
    borderColor: str | None = None
    borderTop: bool | None = None
    borderRight: bool | None = None
    borderBottom: bool | None = None
    borderLeft: bool | None = None
    horizontalAlign: str | None = None
    verticalAlign: str | None = None


class FrReportFieldBindingRead(BaseModel):
    dataset: str | None = None
    field: str | None = None
    expression: str
    aggregation: str | None = None


class FrReportConditionRead(BaseModel):
    column: str | None = None
    operator: str | None = None
    value: str | None = None
    join: str | None = None


class FrReportDataColumnRead(BaseModel):
    dataset: str | None = None
    field: str | None = None
    parentCell: str | None = None
    aggregation: str | None = None
    expandDirection: str | None = None
    customDisplay: str | None = None
    horizontalExtendable: bool | None = None
    verticalExtendable: bool | None = None
    conditions: list[FrReportConditionRead] = Field(default_factory=list)


class FrReportCellWidgetRead(BaseModel):
    widgetClass: str | None = None
    widgetType: str | None = None
    widgetName: str | None = None
    description: str | None = None


class FrReportSubmitColumnRead(BaseModel):
    column: str
    value: str | None = None
    isKey: bool = False
    skipUnmodified: bool = False
    cell: str | None = None


class FrReportSubmitBindingRead(BaseModel):
    name: str | None = None
    database: str | None = None
    schemaName: str | None = None
    tableName: str | None = None
    submitterClass: str | None = None
    columns: list[FrReportSubmitColumnRead] = Field(default_factory=list)


class FrReportCellRead(BaseModel):
    row: int
    column: int
    address: str
    text: str | None = None
    formula: str | None = None
    fieldBinding: FrReportFieldBindingRead | None = None
    dataColumn: FrReportDataColumnRead | None = None
    widget: FrReportCellWidgetRead | None = None
    submitBindings: list[FrReportSubmitBindingRead] = Field(default_factory=list)
    rowSpan: int = 1
    colSpan: int = 1
    expandDirection: str | None = None
    style: FrReportCellStyleRead = Field(default_factory=FrReportCellStyleRead)
    rawTag: str | None = None
    rawPath: str | None = None


class FrReportMergeRead(BaseModel):
    startRow: int
    startColumn: int
    endRow: int
    endColumn: int


class FrReportDimensionRead(BaseModel):
    index: int
    size: int | None = None


class FrReportSheetRead(BaseModel):
    name: str
    rowCount: int
    columnCount: int
    rows: list[FrReportDimensionRead] = Field(default_factory=list)
    columns: list[FrReportDimensionRead] = Field(default_factory=list)
    cells: list[FrReportCellRead] = Field(default_factory=list)
    merges: list[FrReportMergeRead] = Field(default_factory=list)
    submitBindings: list[FrReportSubmitBindingRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FrReportDocumentRead(BaseModel):
    title: str | None = None
    sheets: list[FrReportSheetRead] = Field(default_factory=list)
    unsupportedNodes: list[str] = Field(default_factory=list)
    parseCoverage: dict[str, int] = Field(default_factory=dict)


class FrReportFileStructureRead(BaseModel):
    objectPath: str
    reportPath: str
    fileName: str
    fileType: str
    size: int | None = None
    etag: str | None = None
    lastModified: datetime | None = None
    format: str
    encoding: str | None = None
    xmlVersion: str | None = None
    releaseVersion: str | None = None
    rootTag: str | None = None
    datasets: list[FrReportDatasetRead] = Field(default_factory=list)
    document: FrReportDocumentRead | None = None
    summary: FrReportStructureSummaryRead = Field(default_factory=FrReportStructureSummaryRead)
    warnings: list[str] = Field(default_factory=list)


class FrReportDatabaseConnectionCreate(BaseModel):
    connectionName: str
    driverKey: str = "sqlserver"
    dbType: str = "sqlserver"
    host: str
    port: int = 1433
    database: str
    username: str
    password: str
    odbcDriver: str | None = None


class FrReportDatabaseConnectionRead(BaseModel):
    connectionName: str
    driverKey: str = "sqlserver"
    driverName: str | None = None
    dbType: str = "sqlserver"
    host: str
    port: int = 1433
    database: str
    username: str
    odbcDriver: str | None = None
    configured: bool = True


class FrReportDatabaseDriverRead(BaseModel):
    driverKey: str
    displayName: str
    dbType: str
    pythonDriver: str
    odbcDriver: str | None = None
    defaultPort: int
    description: str | None = None


class FrReportDatasetPreviewParameter(BaseModel):
    name: str
    value: str | int | float | bool | None = None


class FrReportDatasetPreviewRequest(BaseModel):
    connectionName: str
    querySql: str
    parameters: list[FrReportDatasetPreviewParameter] = Field(default_factory=list)
    maxRows: int = 20


class FrReportDatasetPreviewResponse(BaseModel):
    connectionName: str
    needsConnection: bool = False
    executed: bool = False
    success: bool = False
    columns: list[str] = Field(default_factory=list)
    sampleRows: list[dict[str, object | None]] = Field(default_factory=list)
    rowCount: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
