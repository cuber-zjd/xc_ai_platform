import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.schemas.fr_ai_report.ai_report import ExcelAnalysisResult
from app.schemas.fr_ai_report.report_dsl import (
    Aggregation,
    DataModelDSL,
    DataModelFieldDSL,
    DatasetDSL,
    DatasetFieldDSL,
    FieldRole,
    LayoutColumnDSL,
    LayoutDSL,
    ParameterDSL,
    ReportDSL,
    ReportRulesDSL,
    ReportType,
)


TABLE_REPORT_TYPES = {
    ReportType.DETAIL_TABLE,
    ReportType.GROUP_TABLE,
    ReportType.PIVOT_TABLE,
}


async def _invoke_json_agent(
    system_prompt: str,
    payload: dict[str, Any],
    agent_name: str,
) -> dict[str, Any] | None:
    try:
        response = await LLMFactory.safe_invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ],
            capability="general",
            temperature=0,
            json_mode=True,
            max_retries=3,
        )
    except Exception as exc:
        logger.warning(f"{agent_name} 大模型调用失败，使用规则兜底：{exc}")
        return None

    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "".join(str(item) for item in content)
    if not isinstance(content, str):
        logger.warning(f"{agent_name} 大模型返回非文本内容，使用规则兜底")
        return None

    try:
        return json.loads(_strip_json_fence(content))
    except json.JSONDecodeError as exc:
        logger.warning(f"{agent_name} 大模型返回 JSON 解析失败，使用规则兜底：{exc}")
        return None


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
        value = re.sub(r"```$", "", value).strip()
    return value


def _compact_analysis(analysis: ExcelAnalysisResult | None) -> dict[str, Any] | None:
    if not analysis:
        return None
    sheets: list[dict[str, Any]] = []
    for sheet in analysis.sheets[:3]:
        sheets.append(
            {
                "sheetName": sheet.sheetName,
                "rowCount": sheet.rowCount,
                "fields": [
                    {
                        "name": field.name,
                        "label": field.label,
                        "type": field.type.value,
                        "role": field.role.value,
                        "sampleValues": field.sampleValues[:3],
                    }
                    for field in sheet.fields[:30]
                ],
                "sampleRows": sheet.sampleRows[:3],
            }
        )
    return {
        "fileName": analysis.fileName,
        "primarySheet": analysis.primarySheet,
        "sheets": sheets,
    }


class RequirementAgent:
    async def summarize(self, requirement: str | None, analysis: ExcelAnalysisResult | None) -> dict[str, Any]:
        fallback = self._rule_summarize(requirement, analysis)
        llm_result = await _invoke_json_agent(
            system_prompt=(
                "你是 FineReport 表格报表需求分析 Agent。"
                "只能规划表格类报表，不规划柱状图、折线图、饼图或任何图表型报表。"
                "输出严格 JSON：summary、reportType、primarySheet、dimensions、measures、reportScope。"
                "reportType 只能是 detail_table、group_table、pivot_table。"
            ),
            payload={
                "requirement": requirement,
                "excelAnalysis": _compact_analysis(analysis),
                "fallback": fallback,
            },
            agent_name="RequirementAgent",
        )
        if not llm_result:
            return fallback

        report_type = llm_result.get("reportType")
        if report_type not in {item.value for item in TABLE_REPORT_TYPES}:
            report_type = fallback["reportType"]

        return {
            "summary": str(llm_result.get("summary") or fallback["summary"]),
            "reportType": report_type,
            "primarySheet": llm_result.get("primarySheet") or fallback.get("primarySheet"),
            "dimensions": list(llm_result.get("dimensions") or fallback["dimensions"])[:8],
            "measures": list(llm_result.get("measures") or fallback["measures"])[:8],
            "reportScope": "table_only",
        }

    def _rule_summarize(self, requirement: str | None, analysis: ExcelAnalysisResult | None) -> dict[str, Any]:
        text = (requirement or "").strip()
        report_type = self._infer_report_type(text)
        primary_sheet = self._primary_sheet(analysis)
        dimensions = [
            field.label
            for field in primary_sheet.fields
            if field.role in {FieldRole.DIMENSION, FieldRole.DATE}
        ] if primary_sheet else []
        measures = [
            field.label
            for field in primary_sheet.fields
            if field.role == FieldRole.MEASURE
        ] if primary_sheet else []
        return {
            "summary": text or "根据上传 Excel 自动生成表格类业务报表。",
            "reportType": report_type.value,
            "primarySheet": primary_sheet.sheetName if primary_sheet else None,
            "dimensions": dimensions[:8],
            "measures": measures[:8],
            "reportScope": "table_only",
        }

    def _infer_report_type(self, text: str) -> ReportType:
        if any(keyword in text for keyword in ["透视", "交叉", "行列", "矩阵", "周报", "pivot"]):
            return ReportType.PIVOT_TABLE
        if any(keyword in text for keyword in ["分组", "汇总", "合计", "按"]):
            return ReportType.GROUP_TABLE
        return ReportType.DETAIL_TABLE

    def _primary_sheet(self, analysis: ExcelAnalysisResult | None):
        if not analysis or not analysis.sheets:
            return None
        return next(
            (sheet for sheet in analysis.sheets if sheet.sheetName == analysis.primarySheet),
            analysis.sheets[0],
        )


class DataModelAgent:
    async def design(
        self,
        table_schema: dict[str, Any] | None,
        analysis: ExcelAnalysisResult | None,
        requirement_summary: dict[str, Any],
    ) -> DataModelDSL:
        fallback = self._rule_design(table_schema, analysis, requirement_summary)
        if table_schema:
            return fallback

        llm_result = await _invoke_json_agent(
            system_prompt=(
                "你是业务报表逻辑数据模型设计 Agent。"
                "根据 Excel 分析和需求设计逻辑表结构。"
                "输出严格 JSON：tableName、dataSourceStatus、fields、createTableSql。"
                "dataSourceStatus 必须为 designed_not_verified。"
                "fields 每项必须包含 name、label、type、role。"
            ),
            payload={
                "requirementSummary": requirement_summary,
                "excelAnalysis": _compact_analysis(analysis),
                "fallback": fallback.model_dump(mode="json"),
            },
            agent_name="DataModelAgent",
        )
        if not llm_result:
            return fallback

        llm_result["dataSourceStatus"] = "designed_not_verified"
        try:
            return DataModelDSL.model_validate(llm_result)
        except ValidationError as exc:
            logger.warning(f"DataModelAgent 结果校验失败，使用规则兜底：{exc}")
            return fallback

    def _rule_design(
        self,
        table_schema: dict[str, Any] | None,
        analysis: ExcelAnalysisResult | None,
        requirement_summary: dict[str, Any],
    ) -> DataModelDSL:
        if table_schema:
            fields = [
                DataModelFieldDSL(
                    name=item["name"],
                    label=item.get("label", item["name"]),
                    type=item.get("type", "string"),
                    role=item.get("role", "dimension"),
                    sourceTable=item.get("sourceTable"),
                    tableAlias=item.get("tableAlias"),
                    sourceField=item.get("sourceField"),
                    sourceType=item.get("sourceType"),
                    nullable=item.get("nullable"),
                )
                for item in table_schema.get("fields", [])
            ]
            if not fields:
                fields = [
                    DataModelFieldDSL(name="id", label="id", type="string", role="dimension"),
                ]
            return DataModelDSL(
                tableName=table_schema.get("tableName", "provided_report_table"),
                dataSourceStatus="provided",
                fields=fields,
                createTableSql=table_schema.get("createTableSql"),
                tables=table_schema.get("tables", []),
                joinHints=table_schema.get("joinHints", []),
            )

        sheet = RequirementAgent()._primary_sheet(analysis)
        table_name = self._table_name(requirement_summary.get("primarySheet") or "ai_report_source")
        fields = [
            DataModelFieldDSL(name=field.name, label=field.label, type=field.type, role=field.role)
            for field in (sheet.fields if sheet else [])
        ]
        return DataModelDSL(
            tableName=table_name,
            dataSourceStatus="designed_not_verified",
            fields=fields,
            createTableSql=self._create_table_sql(table_name, fields),
        )

    def _table_name(self, source_name: str) -> str:
        normalized = "".join(
            char if char.isascii() and char.isalnum() else "_"
            for char in source_name
        ).strip("_").lower()
        return f"ai_report_{normalized or 'source'}"

    def _create_table_sql(self, table_name: str, fields: list[DataModelFieldDSL]) -> str:
        columns = [f"    {field.name} {self._sql_type(field.type)}" for field in fields]
        return f"CREATE TABLE {table_name} (\n" + ",\n".join(columns) + "\n);"

    def _sql_type(self, field_type: str) -> str:
        mapping = {
            "integer": "BIGINT",
            "decimal": "DECIMAL(18, 4)",
            "date": "DATE",
            "datetime": "TIMESTAMP",
            "boolean": "BOOLEAN",
        }
        return mapping.get(str(field_type), "VARCHAR(255)")


class SqlAgent:
    async def generate(
        self,
        data_model: DataModelDSL,
        parameters: list[ParameterDSL],
        report_type: ReportType,
        requirement_summary: dict[str, Any],
    ) -> str:
        fallback = self._rule_generate(data_model, parameters, report_type)
        llm_result = await _invoke_json_agent(
            system_prompt=(
                "你是报表 SQL Agent。"
                "只生成 SQL Server/T-SQL 的 SELECT 或 WITH 查询 SQL，不允许 DDL/DML/存储过程/多语句。"
                "如果 dataModel.tables 存在，必须只使用其中列出的表、别名和字段，并优先使用 joinHints 或用户需求中明确给出的关联关系生成 JOIN。"
                "不要臆造不存在的表名、字段名或关联条件。"
                "SQL 必须使用 ${parameterName} 绑定所有报表参数。"
                "输出严格 JSON：sql。"
            ),
            payload={
                "requirementSummary": requirement_summary,
                "dataModel": data_model.model_dump(mode="json"),
                "parameters": [item.model_dump(mode="json") for item in parameters],
                "reportType": report_type.value,
                "fallbackSql": fallback,
            },
            agent_name="SqlAgent",
        )
        sql = str((llm_result or {}).get("sql") or "").strip()
        if self._is_safe_sql(sql, parameters):
            return sql
        return fallback

    async def repair(
        self,
        original_sql: str,
        validation_errors: list[str],
        data_model: DataModelDSL,
        parameters: list[ParameterDSL],
        report_type: ReportType,
        requirement_summary: dict[str, Any],
    ) -> str:
        llm_result = await _invoke_json_agent(
            system_prompt=(
                "你是 SQL Server 报表 SQL 修复 Agent。"
                "根据数据库执行错误修复查询，只能输出 SELECT 或 WITH 查询。"
                "必须使用 SQL Server/T-SQL 语法，不允许 DDL/DML/存储过程/多语句。"
                "报表参数必须保留为 ${parameterName} 占位符。"
                "输出严格 JSON：sql。"
            ),
            payload={
                "requirementSummary": requirement_summary,
                "dataModel": data_model.model_dump(mode="json"),
                "parameters": [item.model_dump(mode="json") for item in parameters],
                "reportType": report_type.value,
                "originalSql": original_sql,
                "validationErrors": validation_errors,
            },
            agent_name="SqlAgentRepair",
        )
        sql = str((llm_result or {}).get("sql") or "").strip()
        if self._is_safe_sql(sql, parameters):
            return sql
        return original_sql

    def _rule_generate(
        self,
        data_model: DataModelDSL,
        parameters: list[ParameterDSL],
        report_type: ReportType,
    ) -> str:
        if data_model.tables:
            return self._rule_generate_join_sql(data_model, parameters, report_type)

        select_fields: list[str] = []
        group_fields = [
            field.name for field in data_model.fields
            if field.role in {FieldRole.DIMENSION, FieldRole.DATE}
        ]
        measure_fields = [
            field.name for field in data_model.fields
            if field.role == FieldRole.MEASURE
        ]

        if report_type in {ReportType.GROUP_TABLE, ReportType.PIVOT_TABLE} and measure_fields:
            select_fields.extend(group_fields[:4])
            select_fields.extend([f"SUM({field}) AS {field}" for field in measure_fields[:6]])
            group_clause = f"\nGROUP BY {', '.join(group_fields[:4])}" if group_fields[:4] else ""
        else:
            select_fields = [field.name for field in data_model.fields[:20]]
            group_clause = ""

        where_clause = self._where_clause(parameters)
        return (
            "SELECT\n    "
            + ",\n    ".join(select_fields or ["*"])
            + f"\nFROM {data_model.tableName}{where_clause}{group_clause}"
        )

    def _rule_generate_join_sql(
        self,
        data_model: DataModelDSL,
        parameters: list[ParameterDSL],
        report_type: ReportType,
    ) -> str:
        available_aliases = {str(table.get("alias")) for table in data_model.tables}
        fields = [
            field
            for field in data_model.fields
            if field.tableAlias in available_aliases and field.sourceField
        ]
        if not data_model.joinHints:
            first_alias = str(data_model.tables[0].get("alias"))
            fields = [field for field in fields if field.tableAlias == first_alias]

        group_fields = [field for field in fields if field.role in {FieldRole.DIMENSION, FieldRole.DATE}]
        measure_fields = [field for field in fields if field.role == FieldRole.MEASURE]

        select_fields: list[str] = []
        group_exprs: list[str] = []
        if report_type in {ReportType.GROUP_TABLE, ReportType.PIVOT_TABLE} and measure_fields:
            for field in group_fields[:4]:
                expr = self._field_expr(field)
                select_fields.append(f"{expr} AS {field.name}")
                group_exprs.append(expr)
            select_fields.extend([f"SUM({self._field_expr(field)}) AS {field.name}" for field in measure_fields[:6]])
        else:
            select_fields = [f"{self._field_expr(field)} AS {field.name}" for field in fields[:20]]

        group_clause = f"\nGROUP BY {', '.join(group_exprs)}" if group_exprs else ""
        where_clause = self._where_clause(parameters)
        return (
            "SELECT\n    "
            + ",\n    ".join(select_fields or ["*"])
            + f"\n{self._from_join_clause(data_model)}{where_clause}{group_clause}"
        )

    def _from_join_clause(self, data_model: DataModelDSL) -> str:
        first_table = data_model.tables[0]
        clause = f"FROM {first_table.get('tableName')} {first_table.get('alias')}"
        joined_aliases = {str(first_table.get("alias"))}
        for table in data_model.tables[1:]:
            alias = str(table.get("alias"))
            hint = next(
                (
                    item
                    for item in data_model.joinHints
                    if item.get("rightAlias") == alias and item.get("leftAlias") in joined_aliases
                ),
                None,
            )
            if not hint:
                continue
            clause += f"\nLEFT JOIN {table.get('tableName')} {alias} ON {hint['expression']}"
            joined_aliases.add(alias)
        return clause

    def _field_expr(self, field: DataModelFieldDSL) -> str:
        if field.tableAlias and field.sourceField:
            return f"{field.tableAlias}.{field.sourceField}"
        return field.name

    def _where_clause(self, parameters: list[ParameterDSL]) -> str:
        if not parameters:
            return ""
        conditions = [
            parameter.bindExpression or f"{parameter.name} = '${{{parameter.name}}}'"
            for parameter in parameters
        ]
        return "\nWHERE " + "\n  AND ".join(conditions)

    def _is_safe_sql(self, sql: str, parameters: list[ParameterDSL]) -> bool:
        if not sql or not re.match(r"^\s*(select|with)\b", sql, re.IGNORECASE):
            return False
        if re.search(
            r"\b(drop|truncate|delete|update|insert|alter|create|merge|exec|execute|grant|revoke)\b",
            sql,
            re.IGNORECASE,
        ):
            return False
        normalized = sql.strip()
        without_trailing = normalized[:-1] if normalized.endswith(";") else normalized
        if ";" in without_trailing:
            return False
        return all(f"${{{parameter.name}}}" in sql for parameter in parameters)


class ReportDesignerAgent:
    async def design(
        self,
        report_name: str,
        requirement_summary: dict[str, Any],
        data_model: DataModelDSL,
        query_sql: str,
    ) -> ReportDSL:
        fallback = self._rule_design(report_name, requirement_summary, data_model, query_sql)
        llm_result = await _invoke_json_agent(
            system_prompt=(
                "你是 FineReport ReportDSL 设计 Agent。"
                "只能输出结构化 ReportDSL JSON，不能输出 CPT、XML 或 FineReport 文件内容。"
                "当前阶段只允许 detail_table、group_table、pivot_table。"
                "layout 需要体现业务表格、分组表或交叉周报；不生成图表配置，chartType 必须为 null。"
            ),
            payload={
                "reportName": report_name,
                "requirementSummary": requirement_summary,
                "dataModel": data_model.model_dump(mode="json"),
                "querySql": query_sql,
                "fallbackDsl": fallback.model_dump(mode="json"),
            },
            agent_name="ReportDesignerAgent",
        )
        if not llm_result:
            return fallback

        llm_result["reportType"] = (
            llm_result.get("reportType")
            if llm_result.get("reportType") in {item.value for item in TABLE_REPORT_TYPES}
            else fallback.reportType.value
        )
        llm_result.setdefault("layout", {})
        llm_result["layout"]["chartType"] = None

        try:
            return ReportDSL.model_validate(llm_result)
        except ValidationError as exc:
            logger.warning(f"ReportDesignerAgent 结果校验失败，使用规则兜底：{exc}")
            return fallback

    def _rule_design(
        self,
        report_name: str,
        requirement_summary: dict[str, Any],
        data_model: DataModelDSL,
        query_sql: str,
    ) -> ReportDSL:
        report_type = ReportType(requirement_summary["reportType"])
        parameters = self.build_parameters(data_model)
        dataset_fields = [
            DatasetFieldDSL(
                name=field.name,
                label=field.label,
                type=field.type,
                role=field.role,
                aggregation=(
                    Aggregation.SUM
                    if field.role == FieldRole.MEASURE and report_type != ReportType.DETAIL_TABLE
                    else Aggregation.NONE
                ),
            )
            for field in data_model.fields[:20]
        ]
        layout_columns = [
            LayoutColumnDSL(
                field=field.name,
                title=field.label,
                type=field.type,
                role=field.role,
                aggregation=(
                    Aggregation.SUM
                    if field.role == FieldRole.MEASURE and report_type != ReportType.DETAIL_TABLE
                    else Aggregation.NONE
                ),
                group=field.role in {FieldRole.DIMENSION, FieldRole.DATE} and report_type != ReportType.DETAIL_TABLE,
            )
            for field in data_model.fields[:12]
        ]
        return ReportDSL(
            reportName=report_name,
            reportType=report_type,
            parameters=parameters,
            dataModel=data_model,
            datasets=[DatasetDSL(name="ds_main", sql=query_sql, fields=dataset_fields)],
            layout=LayoutDSL(
                dataset="ds_main",
                columns=layout_columns,
                rowGroupFields=[
                    field.name for field in data_model.fields
                    if field.role in {FieldRole.DIMENSION, FieldRole.DATE}
                ][:3],
                valueFields=[
                    field.name for field in data_model.fields
                    if field.role == FieldRole.MEASURE
                ][:8],
                chartType=None,
            ),
            rules=ReportRulesDSL(),
        )

    def build_parameters(self, data_model: DataModelDSL) -> list[ParameterDSL]:
        date_field = next((field for field in data_model.fields if field.role == FieldRole.DATE), None)
        if not date_field:
            return []
        return [
            ParameterDSL(
                name="start_date",
                label="开始日期",
                type=date_field.type,
                bindExpression=f"{date_field.name} >= '${{start_date}}'",
            ),
            ParameterDSL(
                name="end_date",
                label="结束日期",
                type=date_field.type,
                bindExpression=f"{date_field.name} <= '${{end_date}}'",
            ),
        ]


requirement_agent = RequirementAgent()
data_model_agent = DataModelAgent()
sql_agent = SqlAgent()
report_designer_agent = ReportDesignerAgent()
