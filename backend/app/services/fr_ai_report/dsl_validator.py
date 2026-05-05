import re

from app.schemas.fr_ai_report.report_dsl import (
    Aggregation,
    FieldRole,
    FieldType,
    ReportDSL,
)


class DslValidationError(ValueError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        super().__init__("ReportDSL 校验失败")
        self.errors = errors
        self.warnings = warnings or []


class DslValidator:
    def validate(self, dsl: ReportDSL) -> list[str]:
        errors: list[str] = []
        warnings: list[str] = []
        dataset_map = {dataset.name: dataset for dataset in dsl.datasets}
        dataset = dataset_map.get(dsl.layout.dataset)
        if dataset is None:
            errors.append(f"layout.dataset={dsl.layout.dataset} 不存在")
            raise DslValidationError(errors, warnings)

        dataset_fields = {field.name: field for field in dataset.fields}
        data_model_fields = {field.name: field for field in dsl.dataModel.fields}

        for column in dsl.layout.columns:
            if column.field not in dataset_fields:
                errors.append(f"布局字段 {column.field} 不存在于数据集 {dataset.name}")
                continue
            dataset_field = dataset_fields[column.field]
            if dataset_field.type != column.type:
                errors.append(f"布局字段 {column.field} 类型与数据集不一致")
            if column.field not in data_model_fields:
                warnings.append(f"布局字段 {column.field} 不存在于 dataModel，可能来自 SQL 计算字段")

        for field_name in dsl.layout.rowGroupFields + dsl.layout.columnGroupFields + dsl.layout.valueFields:
            if field_name not in dataset_fields:
                errors.append(f"分组或指标字段 {field_name} 不存在于数据集")

        for parameter in dsl.parameters:
            if f"${{{parameter.name}}}" not in dataset.sql:
                errors.append(f"参数 {parameter.name} 未在 SQL 中以 ${{{parameter.name}}} 形式绑定")

        for field in dataset.fields:
            if field.aggregation != Aggregation.NONE and field.role != FieldRole.MEASURE:
                errors.append(f"字段 {field.name} 非 measure，不允许聚合 {field.aggregation}")
            if field.aggregation in {Aggregation.SUM, Aggregation.AVG} and field.type not in {FieldType.INTEGER, FieldType.DECIMAL}:
                errors.append(f"字段 {field.name} 类型为 {field.type}，不支持 {field.aggregation} 聚合")

        for rule in dsl.rules.conditionalFormats:
            if rule.field not in dataset_fields:
                errors.append(f"条件格式字段 {rule.field} 不存在于数据集")

        unsafe_sql = re.search(r"\b(drop|truncate|delete|update|insert|alter|create)\b", dataset.sql, re.IGNORECASE)
        if unsafe_sql:
            errors.append("数据集 SQL 只允许查询语句，不允许 DDL/DML")

        if errors:
            raise DslValidationError(errors, warnings)
        return warnings


dsl_validator = DslValidator()
