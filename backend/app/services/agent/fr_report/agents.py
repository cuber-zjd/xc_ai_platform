import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.schemas.agent.fr_report.ai_report import ExcelAnalysisResult
from app.schemas.agent.fr_report.report_dsl import (
    Aggregation,
    DataModelDSL,
    DataModelFieldDSL,
    DatasetDSL,
    DatasetFieldDSL,
    FieldRole,
    FieldType,
    HorizontalExpansionDSL,
    LayoutColumnDSL,
    LayoutDSL,
    ParameterDSL,
    ReportDSL,
    ReportMetaDSL,
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
            capability="complex-reasoning",
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
                "templateAnalysis": sheet.templateAnalysis,
            }
        )
    return {
        "fileName": analysis.fileName,
        "primarySheet": analysis.primarySheet,
        "sheets": sheets,
    }


class RequirementAgent:
    async def summarize(
        self, requirement: str | None, analysis: ExcelAnalysisResult | None
    ) -> dict[str, Any]:
        fallback = self._rule_summarize(requirement, analysis)
        llm_result = await _invoke_json_agent(
            system_prompt=(
                "你是 FineReport 表格报表需求分析 Agent。"
                "只能规划表格类报表，不规划柱状图、折线图、饼图或任何图表型报表。"
                "如果 Excel 模板存在市场、城市、区域等横向表头，应优先判断为 FineReport 横向扩展布局，而不是要求 SQL 转宽表。"
                "输出严格 JSON：summary、reportType、primarySheet、dimensions、measures、reportScope、layoutIntent、sqlShape。"
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

        template_design = dict(fallback.get("templateDesign") or {})
        template_design.update(llm_result.get("templateDesign") or {})

        return {
            "summary": str(llm_result.get("summary") or fallback["summary"]),
            "reportType": report_type,
            "primarySheet": llm_result.get("primarySheet")
            or fallback.get("primarySheet"),
            "dimensions": list(llm_result.get("dimensions") or fallback["dimensions"])[
                :8
            ],
            "measures": list(llm_result.get("measures") or fallback["measures"])[:8],
            "reportScope": "table_only",
            "layoutIntent": llm_result.get("layoutIntent")
            or fallback.get("layoutIntent"),
            "sqlShape": llm_result.get("sqlShape") or fallback.get("sqlShape"),
            "templateDesign": template_design,
        }

    def _rule_summarize(
        self, requirement: str | None, analysis: ExcelAnalysisResult | None
    ) -> dict[str, Any]:
        text = (requirement or "").strip()
        report_type = self._infer_report_type(text)
        primary_sheet = self._primary_sheet(analysis)
        dimensions = (
            [
                field.label
                for field in primary_sheet.fields
                if field.role in {FieldRole.DIMENSION, FieldRole.DATE}
            ]
            if primary_sheet
            else []
        )
        measures = (
            [
                field.label
                for field in primary_sheet.fields
                if field.role == FieldRole.MEASURE
            ]
            if primary_sheet
            else []
        )
        template = (
            primary_sheet.templateAnalysis
            if primary_sheet and primary_sheet.templateAnalysis
            else {}
        )
        horizontal_expansion = template.get("horizontalExpansion") or {}
        if horizontal_expansion.get("enabled"):
            report_type = ReportType.PIVOT_TABLE
        return {
            "summary": text or "根据上传 Excel 自动生成表格类业务报表。",
            "reportType": report_type.value,
            "primarySheet": primary_sheet.sheetName if primary_sheet else None,
            "dimensions": dimensions[:8],
            "measures": measures[:8],
            "reportScope": "table_only",
            "layoutIntent": (
                "horizontal_expand_table"
                if horizontal_expansion.get("enabled")
                else "standard_table"
            ),
            "sqlShape": horizontal_expansion.get("sqlShape") or "report_table",
            "templateDesign": {
                "title": template.get("title"),
                "unit": template.get("unit"),
                "updateText": template.get("updateText"),
                "averageLabel": template.get("averageLabel"),
                "notes": template.get("notes", []),
                "filters": template.get("filters", []),
                "horizontalExpansion": horizontal_expansion,
                "dateFormatHints": template.get("dateFormatHints", []),
                "calculationRules": template.get("calculationRules", []),
            },
        }

    def _infer_report_type(self, text: str) -> ReportType:
        if any(
            keyword in text
            for keyword in ["透视", "交叉", "行列", "矩阵", "周报", "pivot"]
        ):
            return ReportType.PIVOT_TABLE
        if any(keyword in text for keyword in ["分组", "汇总", "合计", "按"]):
            return ReportType.GROUP_TABLE
        return ReportType.DETAIL_TABLE

    def _primary_sheet(self, analysis: ExcelAnalysisResult | None):
        if not analysis or not analysis.sheets:
            return None
        return next(
            (
                sheet
                for sheet in analysis.sheets
                if sheet.sheetName == analysis.primarySheet
            ),
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
                "如果 requirementSummary.businessPlan 中包含维护表建议，应优先把这些表作为生产候选数据表纳入 createTableSql、tables 和 joinHints。"
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
                    format=item.get("format"),
                    sourceTable=item.get("sourceTable"),
                    tableAlias=item.get("tableAlias"),
                    sourceField=item.get("sourceField"),
                    sourceType=item.get("sourceType"),
                    nullable=item.get("nullable"),
                )
                for item in table_schema.get("fields", [])
            ]
            if not fields:
                raise ValueError(
                    "已提供数据表但缺少字段结构，请启用 SQL Server 表结构查询或传入 fields"
                )
            return DataModelDSL(
                tableName=table_schema.get("tableName", "provided_report_table"),
                dataSourceStatus="provided",
                fields=fields,
                createTableSql=table_schema.get("createTableSql"),
                tables=table_schema.get("tables", []),
                joinHints=table_schema.get("joinHints", []),
            )

        if (requirement_summary.get("businessPlan") or {}).get("scenario") == "futures_operation_ledger":
            return self._future_ledger_model()

        sheet = RequirementAgent()._primary_sheet(analysis)
        table_name = self._table_name(
            requirement_summary.get("primarySheet") or "ai_report_source"
        )
        fields = [
            DataModelFieldDSL(
                name=field.name, label=field.label, type=field.type, role=field.role
            )
            for field in (sheet.fields if sheet else [])
        ]
        return DataModelDSL(
            tableName=table_name,
            dataSourceStatus="designed_not_verified",
            fields=fields,
            createTableSql=self._create_table_sql(table_name, fields),
        )

    def _table_name(self, source_name: str) -> str:
        normalized = (
            "".join(
                char if char.isascii() and char.isalnum() else "_"
                for char in source_name
            )
            .strip("_")
            .lower()
        )
        return f"ai_report_{normalized or 'source'}"

    def _create_table_sql(
        self, table_name: str, fields: list[DataModelFieldDSL]
    ) -> str:
        columns = [f"    {field.name} {self._sql_type(field.type)}" for field in fields]
        return f"CREATE TABLE {table_name} (\n" + ",\n".join(columns) + "\n);"

    def _future_ledger_model(self) -> DataModelDSL:
        fields = [
            DataModelFieldDSL(name="account_name", label="账户名称", type=FieldType.STRING, role=FieldRole.DIMENSION, sourceTable="fr_future_contract_base", tableAlias="b", sourceField="account_name"),
            DataModelFieldDSL(name="contract_variety", label="合约品种", type=FieldType.STRING, role=FieldRole.DIMENSION, sourceTable="fr_future_contract_base", tableAlias="b", sourceField="contract_variety"),
            DataModelFieldDSL(name="contract_code", label="合约代码", type=FieldType.STRING, role=FieldRole.DIMENSION, sourceTable="fr_future_contract_base", tableAlias="b", sourceField="contract_code"),
            DataModelFieldDSL(name="strategy_type", label="策略类型", type=FieldType.STRING, role=FieldRole.DIMENSION, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="strategy_type"),
            DataModelFieldDSL(name="operation_unit", label="操作单位", type=FieldType.STRING, role=FieldRole.DIMENSION, sourceTable="fr_future_contract_base", tableAlias="b", sourceField="operation_unit"),
            DataModelFieldDSL(name="open_trade_date", label="开仓交易日期", type=FieldType.DATE, role=FieldRole.DATE, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="open_date"),
            DataModelFieldDSL(name="open_direction", label="开仓方向", type=FieldType.STRING, role=FieldRole.DIMENSION, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="open_direction"),
            DataModelFieldDSL(name="open_quantity_lot", label="开仓数量（手）", type=FieldType.DECIMAL, role=FieldRole.MEASURE, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="open_quantity_lot"),
            DataModelFieldDSL(name="open_price", label="开仓价格（元/吨）", type=FieldType.DECIMAL, role=FieldRole.MEASURE, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="open_price"),
            DataModelFieldDSL(name="open_fee_per_lot", label="开仓手续费（元/手）", type=FieldType.DECIMAL, role=FieldRole.MEASURE, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="open_fee_per_lot"),
            DataModelFieldDSL(name="close_trade_date", label="平仓交易日期", type=FieldType.DATE, role=FieldRole.DATE, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="close_date"),
            DataModelFieldDSL(name="close_direction", label="平仓方向", type=FieldType.STRING, role=FieldRole.DIMENSION, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="close_direction"),
            DataModelFieldDSL(name="close_quantity_lot", label="平仓数量（手）", type=FieldType.DECIMAL, role=FieldRole.MEASURE, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="close_quantity_lot"),
            DataModelFieldDSL(name="close_price", label="平仓价格（元/吨）", type=FieldType.DECIMAL, role=FieldRole.MEASURE, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="close_price"),
            DataModelFieldDSL(name="close_fee_per_lot", label="平仓手续费（元/手）", type=FieldType.DECIMAL, role=FieldRole.MEASURE, sourceTable="fr_future_trade_ledger", tableAlias="t", sourceField="close_fee_per_lot"),
            DataModelFieldDSL(name="realized_profit", label="平仓盈亏（元）", type=FieldType.DECIMAL, role=FieldRole.MEASURE),
            DataModelFieldDSL(name="position_direction", label="持仓方向", type=FieldType.STRING, role=FieldRole.DIMENSION),
            DataModelFieldDSL(name="remaining_quantity_lot", label="持仓数量（手）", type=FieldType.DECIMAL, role=FieldRole.MEASURE),
            DataModelFieldDSL(name="settlement_price", label="收盘价（元/吨）", type=FieldType.DECIMAL, role=FieldRole.MEASURE, sourceTable="fr_future_settlement_price", tableAlias="p", sourceField="settlement_price"),
            DataModelFieldDSL(name="floating_profit", label="浮动盈亏（元）", type=FieldType.DECIMAL, role=FieldRole.MEASURE),
        ]
        return DataModelDSL(
            tableName="fr_future_trade_ledger",
            dataSourceStatus="designed_not_verified",
            fields=fields,
            createTableSql=self._future_create_table_sql(),
            tables=[
                {"tableName": "fr_future_trade_ledger", "alias": "t", "displayName": "期货操作台账"},
                {"tableName": "fr_future_contract_base", "alias": "b", "displayName": "期货合约基础资料"},
                {"tableName": "fr_future_settlement_price", "alias": "p", "displayName": "期货每日收盘价维护"},
            ],
            joinHints=[
                {"leftAlias": "t", "rightAlias": "b", "expression": "t.account_name = b.account_name AND t.contract_variety = b.contract_variety AND t.contract_code = b.contract_code"},
                {"leftAlias": "t", "rightAlias": "p", "expression": "t.contract_code = p.contract_code AND p.price_date = '${end_date}'"},
            ],
        )

    def _future_create_table_sql(self) -> str:
        return """IF OBJECT_ID('dbo.fr_future_contract_base', 'U') IS NULL
CREATE TABLE dbo.fr_future_contract_base (
    account_name VARCHAR(100) NOT NULL,
    contract_variety VARCHAR(100) NOT NULL,
    contract_code VARCHAR(60) NOT NULL,
    tons_per_lot DECIMAL(18, 4) NOT NULL,
    operation_unit VARCHAR(60) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    CONSTRAINT pk_future_contract_base PRIMARY KEY (account_name, contract_variety, contract_code)
);

IF OBJECT_ID('dbo.fr_future_trade_ledger', 'U') IS NULL
CREATE TABLE dbo.fr_future_trade_ledger (
    ledger_id VARCHAR(80) NOT NULL PRIMARY KEY,
    account_name VARCHAR(100) NOT NULL,
    contract_variety VARCHAR(100) NOT NULL,
    contract_code VARCHAR(60) NOT NULL,
    strategy_type VARCHAR(40) NOT NULL,
    operation_unit VARCHAR(60) NULL,
    open_date DATE NOT NULL,
    open_direction VARCHAR(20) NOT NULL,
    open_quantity_lot DECIMAL(18, 4) NOT NULL,
    open_price DECIMAL(18, 4) NOT NULL,
    close_date DATE NULL,
    close_direction VARCHAR(20) NULL,
    close_quantity_lot DECIMAL(18, 4) NOT NULL DEFAULT 0,
    close_price DECIMAL(18, 4) NULL,
    open_fee_per_lot DECIMAL(18, 4) NOT NULL DEFAULT 0,
    close_fee_per_lot DECIMAL(18, 4) NOT NULL DEFAULT 0,
    CONSTRAINT ck_future_close_qty CHECK (close_quantity_lot <= open_quantity_lot)
);

IF OBJECT_ID('dbo.fr_future_settlement_price', 'U') IS NULL
CREATE TABLE dbo.fr_future_settlement_price (
    price_date DATE NOT NULL,
    contract_code VARCHAR(60) NOT NULL,
    settlement_price DECIMAL(18, 4) NOT NULL,
    CONSTRAINT uk_future_settlement_price UNIQUE (price_date, contract_code)
);"""

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
        fallback = self._rule_generate(
            data_model, parameters, report_type, requirement_summary
        )
        llm_result = await _invoke_json_agent(
            system_prompt=(
                "你是报表 SQL Agent。"
                "只生成 SQL Server/T-SQL 的 SELECT 或 WITH 查询 SQL，不允许 DDL/DML/存储过程/多语句。"
                "如果 dataModel.tables 存在，必须只使用其中列出的表、别名和字段，并优先使用 joinHints 或用户需求中明确给出的关联关系生成 JOIN。"
                "不要臆造不存在的表名、字段名或关联条件。"
                "当需求摘要 sqlShape=long_table_preferred 或模板存在横向扩展时，SQL 应保持明细长表字段，例如 record_date、market、price、change_amt。"
                "不要为了复刻 Excel 城市横向列而生成大量 CASE WHEN/PIVOT/SUM 宽表列；这类横向展开交给 FineReport 设计器的横向扩展处理。"
                "SQL 必须使用 ${parameterName} 绑定所有报表参数。"
                "只能使用 parameters 列表中已经定义的参数，不允许自行新增 ${market}、${product}、${grade} 等占位符。"
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
                "只能使用 parameters 列表中已经定义的参数，不允许自行新增未定义占位符。"
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
        requirement_summary: dict[str, Any],
    ) -> str:
        if (requirement_summary.get("businessPlan") or {}).get("scenario") == "futures_operation_ledger":
            return self._future_ledger_sql()

        if data_model.tables:
            return self._rule_generate_join_sql(
                data_model, parameters, report_type, requirement_summary
            )

        select_fields: list[str] = []
        group_fields = [
            field.name
            for field in data_model.fields
            if field.role in {FieldRole.DIMENSION, FieldRole.DATE}
        ]
        measure_fields = [
            field.name for field in data_model.fields if field.role == FieldRole.MEASURE
        ]

        if self._should_preserve_long_table(data_model, requirement_summary):
            select_fields = [
                field.name for field in self._long_table_fields(data_model)[:20]
            ]
            group_clause = ""
        elif (
            report_type in {ReportType.GROUP_TABLE, ReportType.PIVOT_TABLE}
            and measure_fields
        ):
            select_fields.extend(group_fields[:4])
            select_fields.extend(
                [f"SUM({field}) AS {field}" for field in measure_fields[:6]]
            )
            group_clause = (
                f"\nGROUP BY {', '.join(group_fields[:4])}" if group_fields[:4] else ""
            )
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
        requirement_summary: dict[str, Any],
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

        group_fields = [
            field
            for field in fields
            if field.role in {FieldRole.DIMENSION, FieldRole.DATE}
        ]
        measure_fields = [field for field in fields if field.role == FieldRole.MEASURE]

        select_fields: list[str] = []
        group_exprs: list[str] = []
        if self._should_preserve_long_table(data_model, requirement_summary):
            select_fields = [
                f"{self._field_expr(field)} AS {field.name}"
                for field in self._long_table_fields(data_model, fields)[:20]
            ]
        elif (
            report_type in {ReportType.GROUP_TABLE, ReportType.PIVOT_TABLE}
            and measure_fields
        ):
            for field in group_fields[:4]:
                expr = self._field_expr(field)
                select_fields.append(f"{expr} AS {field.name}")
                group_exprs.append(expr)
            select_fields.extend(
                [
                    f"SUM({self._field_expr(field)}) AS {field.name}"
                    for field in measure_fields[:6]
                ]
            )
        else:
            select_fields = [
                f"{self._field_expr(field)} AS {field.name}" for field in fields[:20]
            ]

        group_clause = f"\nGROUP BY {', '.join(group_exprs)}" if group_exprs else ""
        where_clause = self._where_clause(parameters)
        return (
            "SELECT\n    "
            + ",\n    ".join(select_fields or ["*"])
            + f"\n{self._from_join_clause(data_model)}{where_clause}{group_clause}"
        )

    def _future_ledger_sql(self) -> str:
        return """WITH __fr_params AS (
    SELECT
        ISNULL(TRY_CONVERT(date, NULLIF('${start_date}', '')), CONVERT(date, '1900-01-01')) AS start_date,
        ISNULL(TRY_CONVERT(date, NULLIF('${end_date}', '')), CONVERT(date, '2099-12-31')) AS end_date
)
SELECT
    b.account_name,
    b.contract_variety,
    b.contract_code,
    t.strategy_type,
    COALESCE(t.operation_unit, b.operation_unit) AS operation_unit,
    t.open_date AS open_trade_date,
    t.open_direction,
    t.open_quantity_lot,
    t.open_price,
    t.open_fee_per_lot,
    t.close_date AS close_trade_date,
    t.close_direction,
    t.close_quantity_lot,
    t.close_price,
    t.close_fee_per_lot,
    CASE
        WHEN t.close_quantity_lot IS NULL OR t.close_quantity_lot = 0 OR t.close_price IS NULL THEN NULL
        WHEN t.open_direction IN ('买', '多', '买入') THEN
            (t.close_price - t.open_price) * t.close_quantity_lot * b.tons_per_lot
            - (t.open_fee_per_lot + t.close_fee_per_lot) * t.close_quantity_lot
        ELSE
            (t.open_price - t.close_price) * t.close_quantity_lot * b.tons_per_lot
            - (t.open_fee_per_lot + t.close_fee_per_lot) * t.close_quantity_lot
    END AS realized_profit,
    CASE WHEN t.open_direction IN ('买', '多', '买入') THEN '多' ELSE '空' END AS position_direction,
    t.open_quantity_lot - COALESCE(t.close_quantity_lot, 0) AS remaining_quantity_lot,
    p.settlement_price,
    CASE
        WHEN p.settlement_price IS NULL THEN NULL
        WHEN t.open_direction IN ('买', '多', '买入') THEN
            (p.settlement_price - t.open_price)
            * (t.open_quantity_lot - COALESCE(t.close_quantity_lot, 0))
            * b.tons_per_lot
        ELSE
            (t.open_price - p.settlement_price)
            * (t.open_quantity_lot - COALESCE(t.close_quantity_lot, 0))
            * b.tons_per_lot
    END AS floating_profit
FROM fr_future_trade_ledger t
INNER JOIN fr_future_contract_base b
    ON t.account_name = b.account_name
    AND t.contract_variety = b.contract_variety
    AND t.contract_code = b.contract_code
LEFT JOIN fr_future_settlement_price p
    ON t.contract_code = p.contract_code
    AND p.price_date = (SELECT end_date FROM __fr_params)
WHERE t.open_date <= (SELECT end_date FROM __fr_params)
  AND (t.close_date IS NULL OR t.close_date >= (SELECT start_date FROM __fr_params))
  AND (NULLIF('${account_name}', '') IS NULL OR b.account_name = '${account_name}')
  AND (NULLIF('${contract_variety}', '') IS NULL OR b.contract_variety = '${contract_variety}')
  AND (NULLIF('${contract_code}', '') IS NULL OR b.contract_code = '${contract_code}')
  AND COALESCE(t.close_quantity_lot, 0) <= t.open_quantity_lot"""

    def _should_preserve_long_table(
        self, data_model: DataModelDSL, requirement_summary: dict[str, Any]
    ) -> bool:
        template_design = requirement_summary.get("templateDesign") or {}
        horizontal_expansion = template_design.get("horizontalExpansion") or {}
        if requirement_summary.get(
            "sqlShape"
        ) == "long_table_preferred" or horizontal_expansion.get("enabled"):
            return True
        labels = {field.label.lower() for field in data_model.fields}
        names = {field.name.lower() for field in data_model.fields}
        has_market = bool(
            {"market", "area", "city", "市场", "地区", "城市"} & (labels | names)
        )
        has_value = bool(
            {"price", "value", "amount", "价格", "数值"} & (labels | names)
        )
        return has_market and has_value

    def _long_table_fields(
        self,
        data_model: DataModelDSL,
        fields: list[DataModelFieldDSL] | None = None,
    ) -> list[DataModelFieldDSL]:
        source_fields = fields or data_model.fields
        priority_keywords = [
            "record_date",
            "date",
            "year",
            "market",
            "area",
            "city",
            "product",
            "grade",
            "pack_type",
            "price",
            "change_amt",
            "remark",
        ]
        ordered: list[DataModelFieldDSL] = []
        for keyword in priority_keywords:
            ordered.extend(
                field
                for field in source_fields
                if field not in ordered
                and (keyword in field.name.lower() or keyword in field.label.lower())
            )
        ordered.extend(field for field in source_fields if field not in ordered)
        return ordered

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
                    if item.get("rightAlias") == alias
                    and item.get("leftAlias") in joined_aliases
                ),
                None,
            )
            if not hint:
                continue
            clause += (
                f"\nLEFT JOIN {table.get('tableName')} {alias} ON {hint['expression']}"
            )
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
        defined_parameters = {parameter.name for parameter in parameters}
        used_parameters = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", sql))
        if used_parameters - defined_parameters:
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
        fallback = self._rule_design(
            report_name, requirement_summary, data_model, query_sql
        )
        llm_result = await _invoke_json_agent(
            system_prompt=(
                "你是 FineReport ReportDSL 设计 Agent。"
                "只能输出结构化 ReportDSL JSON，不能输出 CPT、XML 或 FineReport 文件内容。"
                "当前阶段只允许 detail_table、group_table、pivot_table。"
                "layout 需要体现业务表格、分组表或交叉周报；不生成图表配置，chartType 必须为 null。"
                "reportMeta 必须承载 Excel 模板语义中的标题、单位、更新时间、均价、备注、筛选条件；不要把这些只塞进 layout.designHints。"
                "如果 querySql 是 record_date/market/price/change_amt 这类长表，应在 layout.columnGroupFields 中放市场字段，valueFields 放价格/涨跌字段，并设置 horizontalExpansion。"
                "不要要求 SQL 已经包含每个城市一个独立字段；城市横向列由 FineReport 横向扩展表达。"
                "如果 requirementSummary.dslRevisionNote 或 templateDesign.designNotes 中要求调整版式，必须优先遵守。"
                "如果要求“涨跌只保留最新一天、单独一行、放在市场下面价格列表上面”，请在 layout.designHints.specialRows 中保留 latest_change_row："
                "kind=latest_change_only，keepRows=1，position=below_column_group_above_price_rows，measureHint=涨跌，dateRule=latest_date。"
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
            if llm_result.get("reportType")
            in {item.value for item in TABLE_REPORT_TYPES}
            else fallback.reportType.value
        )
        llm_result.setdefault("layout", {})
        llm_result["layout"]["chartType"] = None

        try:
            return self._normalize_futures_layout(
                ReportDSL.model_validate(llm_result),
                requirement_summary,
                data_model,
            )
        except ValidationError as exc:
            logger.warning(f"ReportDesignerAgent 结果校验失败，使用规则兜底：{exc}")
            return self._normalize_futures_layout(fallback, requirement_summary, data_model)

    def _rule_design(
        self,
        report_name: str,
        requirement_summary: dict[str, Any],
        data_model: DataModelDSL,
        query_sql: str,
    ) -> ReportDSL:
        report_type = ReportType(requirement_summary["reportType"])
        parameters = self.build_parameters(data_model)
        horizontal = self._horizontal_expansion_from_summary(
            requirement_summary, data_model
        )
        column_group_fields = (
            [horizontal.dimensionField]
            if horizontal and horizontal.dimensionField
            else []
        )
        value_field_names = (
            horizontal.valueFields
            if horizontal
            else [
                field.name
                for field in data_model.fields
                if field.role == FieldRole.MEASURE
            ][:8]
        )
        row_group_names = [
            field.name
            for field in data_model.fields
            if field.role in {FieldRole.DIMENSION, FieldRole.DATE}
            and field.name not in column_group_fields
        ][:3]
        dataset_fields = [
            DatasetFieldDSL(
                name=field.name,
                label=field.label,
                type=field.type,
                role=field.role,
                aggregation=(
                    Aggregation.SUM
                    if field.role == FieldRole.MEASURE
                    and report_type != ReportType.DETAIL_TABLE
                    else Aggregation.NONE
                ),
            )
            for field in data_model.fields[:20]
        ]
        column_limit = 20 if (requirement_summary.get("businessPlan") or {}).get("scenario") == "futures_operation_ledger" else 12
        layout_columns = [
            LayoutColumnDSL(
                field=field.name,
                title=field.label,
                type=field.type,
                role=field.role,
                aggregation=(
                    Aggregation.SUM
                    if field.role == FieldRole.MEASURE
                    and report_type != ReportType.DETAIL_TABLE
                    else Aggregation.NONE
                ),
                format=field.format or self._default_format(field),
                group=field.name in row_group_names + column_group_fields,
                expandDirection=(
                    "right"
                    if field.name in column_group_fields
                    or (horizontal and field.name in value_field_names)
                    else "down"
                ),
            )
            for field in data_model.fields[:column_limit]
        ]
        design_hints = dict(requirement_summary.get("templateDesign") or {})
        if (requirement_summary.get("businessPlan") or {}).get("scenario") == "futures_operation_ledger":
            design_hints["headerGroups"] = [
                {"label": "", "fields": ["account_name", "contract_variety", "contract_code", "strategy_type"]},
                {
                    "label": "开仓",
                    "fields": ["open_trade_date", "open_direction", "open_quantity_lot", "open_price", "open_fee_per_lot"],
                },
                {
                    "label": "平仓",
                    "fields": [
                        "close_trade_date",
                        "close_direction",
                        "close_quantity_lot",
                        "close_price",
                        "close_fee_per_lot",
                        "realized_profit",
                    ],
                },
                {
                    "label": "持仓",
                    "fields": ["position_direction", "remaining_quantity_lot", "settlement_price", "floating_profit"],
                },
                {"label": "", "fields": ["operation_unit"]},
            ]
        if self._requires_latest_change_row(requirement_summary):
            special_rows = list(design_hints.get("specialRows") or [])
            if not any(item.get("id") == "latest_change_row" for item in special_rows if isinstance(item, dict)):
                special_rows.append(
                    {
                        "id": "latest_change_row",
                        "label": "涨跌",
                        "kind": "latest_change_only",
                        "keepRows": 1,
                        "position": "below_column_group_above_price_rows",
                        "dimensionHint": "市场",
                        "measureHint": "涨跌",
                        "dateRule": "latest_date",
                    }
                )
            design_hints["specialRows"] = special_rows

        return self._normalize_futures_layout(ReportDSL(
            reportName=report_name,
            reportType=report_type,
            reportMeta=self._report_meta(report_name, requirement_summary),
            parameters=parameters,
            dataModel=data_model,
            datasets=[DatasetDSL(name="ds_main", sql=query_sql, fields=dataset_fields)],
            layout=LayoutDSL(
                dataset="ds_main",
                columns=layout_columns,
                rowGroupFields=row_group_names,
                columnGroupFields=column_group_fields,
                valueFields=value_field_names,
                horizontalExpansion=horizontal,
                designHints=design_hints,
                chartType=None,
            ),
            rules=ReportRulesDSL(),
        ), requirement_summary, data_model)

    def _normalize_futures_layout(
        self,
        dsl: ReportDSL,
        requirement_summary: dict[str, Any],
        data_model: DataModelDSL,
    ) -> ReportDSL:
        if (requirement_summary.get("businessPlan") or {}).get("scenario") != "futures_operation_ledger":
            return dsl
        field_map = {field.name: field for field in data_model.fields}
        ordered_fields = [
            "account_name",
            "contract_variety",
            "contract_code",
            "strategy_type",
            "open_trade_date",
            "open_direction",
            "open_quantity_lot",
            "open_price",
            "open_fee_per_lot",
            "close_trade_date",
            "close_direction",
            "close_quantity_lot",
            "close_price",
            "close_fee_per_lot",
            "realized_profit",
            "position_direction",
            "remaining_quantity_lot",
            "settlement_price",
            "floating_profit",
        ]
        columns: list[LayoutColumnDSL] = []
        existing = {column.field: column for column in dsl.layout.columns}
        for field_name in ordered_fields:
            field = field_map.get(field_name)
            if not field:
                continue
            source_column = existing.get(field_name)
            columns.append(
                source_column
                or LayoutColumnDSL(
                    field=field.name,
                    title=field.label,
                    width=self._future_column_width(field.name),
                    type=field.type,
                    role=field.role,
                    format=field.format or self._default_format(field),
                    expandDirection="down",
                )
            )
        dsl.layout.columns = columns
        dsl.layout.designHints["headerGroups"] = self._future_header_groups()
        existing_parameters = {parameter.name for parameter in dsl.parameters}
        for parameter in [
            ParameterDSL(
                name="account_name",
                label="账户名称",
                type=FieldType.STRING,
                bindExpression="account_name = '${account_name}'",
            ),
            ParameterDSL(
                name="contract_variety",
                label="合约品种",
                type=FieldType.STRING,
                bindExpression="contract_variety = '${contract_variety}'",
            ),
            ParameterDSL(
                name="contract_code",
                label="合约代码",
                type=FieldType.STRING,
                bindExpression="contract_code = '${contract_code}'",
            ),
        ]:
            if parameter.name not in existing_parameters:
                dsl.parameters.append(parameter)
        return dsl

    def _future_column_width(self, field_name: str) -> int:
        wide = {"contract_variety", "strategy_type", "realized_profit", "floating_profit"}
        narrow = {"open_direction", "close_direction", "position_direction"}
        if field_name in wide:
            return 150
        if field_name in narrow:
            return 80
        return 120

    def _future_header_groups(self) -> list[dict[str, object]]:
        return [
            {"label": "", "fields": ["account_name", "contract_variety", "contract_code", "strategy_type"]},
            {
                "label": "开仓",
                "fields": ["open_trade_date", "open_direction", "open_quantity_lot", "open_price", "open_fee_per_lot"],
            },
            {
                "label": "平仓",
                "fields": [
                    "close_trade_date",
                    "close_direction",
                    "close_quantity_lot",
                    "close_price",
                    "close_fee_per_lot",
                    "realized_profit",
                ],
            },
            {
                "label": "持仓",
                "fields": ["position_direction", "remaining_quantity_lot", "settlement_price", "floating_profit"],
            },
        ]

    def _report_meta(self, report_name: str, requirement_summary: dict[str, Any]) -> ReportMetaDSL:
        template_design = requirement_summary.get("templateDesign") or {}
        notes = template_design.get("notes") or template_design.get("remarks") or []
        filters = template_design.get("filters") or []
        return ReportMetaDSL(
            title=template_design.get("title") or report_name,
            unit=template_design.get("unit"),
            updateText=template_design.get("updateText"),
            averageLabel=template_design.get("averageLabel"),
            remarks=[str(item) for item in notes if str(item).strip()][:12],
            filters=filters if isinstance(filters, list) else [],
        )

    def build_parameters(self, data_model: DataModelDSL) -> list[ParameterDSL]:
        date_field = next(
            (field for field in data_model.fields if field.role == FieldRole.DATE), None
        )
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

    def _horizontal_expansion_from_summary(
        self,
        requirement_summary: dict[str, Any],
        data_model: DataModelDSL,
    ) -> HorizontalExpansionDSL | None:
        template_design = requirement_summary.get("templateDesign") or {}
        expansion = template_design.get("horizontalExpansion") or {}
        if not expansion.get("enabled"):
            return None
        dimension = self._find_field(
            data_model,
            ["market", "area", "city", "市场", "地区", "城市"],
            FieldRole.DIMENSION,
        )
        value_fields = [
            field.name
            for field in data_model.fields
            if field.role == FieldRole.MEASURE
            and any(
                keyword in field.name.lower() or keyword in field.label.lower()
                for keyword in ["price", "value", "amount", "change", "价格", "涨跌"]
            )
        ][:4]
        if not dimension or not value_fields:
            return None
        return HorizontalExpansionDSL(
            enabled=True,
            dimensionField=dimension.name,
            valueFields=value_fields,
            sourceLabels=list(expansion.get("sourceLabels") or [])[:30],
        )

    def _find_field(
        self,
        data_model: DataModelDSL,
        keywords: list[str],
        role: FieldRole | None = None,
    ) -> DataModelFieldDSL | None:
        for field in data_model.fields:
            if role and field.role != role:
                continue
            text = f"{field.name} {field.label}".lower()
            if any(keyword.lower() in text for keyword in keywords):
                return field
        return None

    def _default_format(self, field: DataModelFieldDSL) -> str | None:
        text = f"{field.name} {field.label}".lower()
        if field.type == "date":
            return "yyyy-MM-dd"
        if any(keyword in text for keyword in ["year", "年份"]):
            return "yyyy年"
        if any(keyword in text for keyword in ["price", "价格"]):
            return "#,##0"
        if any(keyword in text for keyword in ["change", "涨跌"]):
            return "#,##0;[Green]-#,##0;0"
        return field.format

    def _requires_latest_change_row(self, requirement_summary: dict[str, Any]) -> bool:
        note = str(requirement_summary.get("dslRevisionNote") or "")
        template_design = requirement_summary.get("templateDesign") or {}
        notes = " ".join(str(item) for item in template_design.get("designNotes") or [])
        text = f"{note} {notes}".replace(" ", "")
        return (
            "涨跌" in text
            and any(keyword in text for keyword in ["最新一天", "最新1天", "最后一天"])
            and any(keyword in text for keyword in ["单独一行", "只保留一行", "保留一行"])
        )


requirement_agent = RequirementAgent()
data_model_agent = DataModelAgent()
sql_agent = SqlAgent()
report_designer_agent = ReportDesignerAgent()
