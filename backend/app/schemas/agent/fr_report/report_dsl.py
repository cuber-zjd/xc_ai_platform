from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ReportType(str, Enum):
    DETAIL_TABLE = "detail_table"
    GROUP_TABLE = "group_table"
    PIVOT_TABLE = "pivot_table"


class FieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"


class FieldRole(str, Enum):
    DIMENSION = "dimension"
    MEASURE = "measure"
    DATE = "date"
    TEXT = "text"


class Aggregation(str, Enum):
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    NONE = "none"


class ParameterDSL(BaseModel):
    name: str
    label: str
    type: FieldType = Field(default=FieldType.STRING)
    required: bool = False
    default: Any | None = None
    bindExpression: str | None = None


class DataModelFieldDSL(BaseModel):
    name: str
    label: str
    type: FieldType
    role: FieldRole
    format: str | None = None
    sourceTable: str | None = None
    tableAlias: str | None = None
    sourceField: str | None = None
    sourceType: str | None = None
    nullable: bool | None = None


class DataModelDSL(BaseModel):
    tableName: str
    dataSourceStatus: Literal["provided", "designed_not_verified"]
    fields: list[DataModelFieldDSL]
    createTableSql: str | None = None
    tables: list[dict[str, Any]] = Field(default_factory=list)
    joinHints: list[dict[str, str]] = Field(default_factory=list)


class DatasetFieldDSL(BaseModel):
    name: str
    label: str
    type: FieldType
    role: FieldRole
    aggregation: Aggregation = Aggregation.NONE


class DatasetDSL(BaseModel):
    name: str
    sql: str
    fields: list[DatasetFieldDSL]


class ReportMetaDSL(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    unit: str | None = None
    updateText: str | None = None
    averageLabel: str | None = None
    remarks: list[str] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)


class LayoutColumnDSL(BaseModel):
    field: str
    title: str
    width: int = Field(default=120, ge=40, le=600)
    type: FieldType
    role: FieldRole
    aggregation: Aggregation = Aggregation.NONE
    format: str | None = None
    group: bool = False
    expandDirection: Literal["down", "right", "none"] = "down"
    hidden: bool = False


class HorizontalExpansionDSL(BaseModel):
    enabled: bool = False
    dimensionField: str | None = None
    valueFields: list[str] = Field(default_factory=list)
    direction: Literal["right"] = "right"
    sourceLabels: list[str] = Field(default_factory=list)


class LayoutDSL(BaseModel):
    dataset: str
    columns: list[LayoutColumnDSL]
    rowGroupFields: list[str] = Field(default_factory=list)
    columnGroupFields: list[str] = Field(default_factory=list)
    valueFields: list[str] = Field(default_factory=list)
    horizontalExpansion: HorizontalExpansionDSL | None = None
    designHints: dict[str, Any] = Field(default_factory=dict)
    chartType: str | None = None


class ConditionalFormatRuleDSL(BaseModel):
    field: str
    operator: Literal[">", ">=", "<", "<=", "=", "!=", "contains"]
    value: Any
    style: dict[str, str] = Field(default_factory=dict)


class ReportRulesDSL(BaseModel):
    conditionalFormats: list[ConditionalFormatRuleDSL] = Field(default_factory=list)
    freezeHeader: bool = True
    showRowNumber: bool = False
    pageSize: int = Field(default=50, ge=1, le=1000)


class CellWidgetDSL(BaseModel):
    field: str
    widgetType: Literal["text", "number", "date", "combo"] = "text"
    widgetName: str | None = None
    dictionaryDataset: str | None = None
    dictionaryKeyField: str | None = None
    dictionaryValueField: str | None = None


class WriteBackColumnDSL(BaseModel):
    columnName: str
    field: str | None = None
    isKey: bool = False
    skipUnmodified: bool = False
    valueFormula: str | None = None


class RowActionDSL(BaseModel):
    enabled: bool = False
    insertLabel: str = "插入行"
    deleteLabel: str = "删除行"
    columnWidth: int = Field(default=70, ge=40, le=160)


class WriteBackDSL(BaseModel):
    enabled: bool = False
    submitterName: str = "内置SQL1"
    databaseName: str | None = None
    schemaName: str = ""
    tableName: str | None = None
    mode: Literal["update"] = "update"
    toolbar: bool = True
    rowActions: RowActionDSL = Field(default_factory=RowActionDSL)
    widgets: list[CellWidgetDSL] = Field(default_factory=list)
    columns: list[WriteBackColumnDSL] = Field(default_factory=list)


class ReportDSL(BaseModel):
    schemaVersion: str = "1.0"
    reportName: str
    reportType: ReportType
    reportMeta: ReportMetaDSL = Field(default_factory=ReportMetaDSL)
    parameters: list[ParameterDSL] = Field(default_factory=list)
    dataModel: DataModelDSL
    datasets: list[DatasetDSL]
    layout: LayoutDSL
    rules: ReportRulesDSL = Field(default_factory=ReportRulesDSL)
    writeBack: WriteBackDSL = Field(default_factory=WriteBackDSL)

    @field_validator("datasets")
    @classmethod
    def validate_dataset_count(cls, value: list[DatasetDSL]) -> list[DatasetDSL]:
        if not value:
            raise ValueError("至少需要一个数据集")
        return value


def report_dsl_json_schema() -> dict[str, Any]:
    return ReportDSL.model_json_schema()
