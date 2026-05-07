from typing import Any

from app.schemas.agent.fr_report.ai_report import ExcelAnalysisResult, SqlValidationResult
from app.schemas.agent.fr_report.report_dsl import DataModelDSL, ParameterDSL, ReportType
from app.services.agent.fr_report.agents import _compact_analysis, _invoke_json_agent, sql_agent
from app.services.agent.fr_report.sqlserver_query_service import sqlserver_query_service


class SqlReActResult:
    def __init__(self, sql: str, validation: SqlValidationResult, logs: list[str]):
        self.sql = sql
        self.validation = validation
        self.logs = logs


class SqlReActAgent:
    async def generate_and_validate(
        self,
        data_model: DataModelDSL,
        parameters: list[ParameterDSL],
        report_type: ReportType,
        requirement_summary: dict[str, Any],
        analysis: ExcelAnalysisResult | None,
        max_iterations: int = 3,
    ) -> SqlReActResult:
        logs: list[str] = []
        table_samples = await sqlserver_query_service.sample_data_model(data_model)
        sql = await sql_agent.generate(data_model, parameters, report_type, requirement_summary)
        validation = await sqlserver_query_service.validate_select_sql(sql, parameters)
        self._apply_template_expectation(validation, analysis)
        logs.append(self._log_iteration(1, validation))

        for iteration in range(2, max_iterations + 1):
            if validation.success:
                break
            if not validation.enabled or not validation.configured:
                break

            repaired_sql = await self._think_and_repair(
                sql=sql,
                validation=validation,
                data_model=data_model,
                parameters=parameters,
                report_type=report_type,
                requirement_summary=requirement_summary,
                analysis=analysis,
                table_samples=table_samples,
                iteration=iteration,
            )
            if not repaired_sql or repaired_sql == sql:
                repaired_sql = await sql_agent.repair(
                    sql,
                    validation.errors,
                    data_model,
                    parameters,
                    report_type,
                    requirement_summary,
                )
            if repaired_sql == sql:
                break

            sql = repaired_sql
            validation = await sqlserver_query_service.validate_select_sql(sql, parameters)
            self._apply_template_expectation(validation, analysis)
            logs.append(self._log_iteration(iteration, validation))

        return SqlReActResult(sql=sql, validation=validation, logs=logs)

    async def _think_and_repair(
        self,
        sql: str,
        validation: SqlValidationResult,
        data_model: DataModelDSL,
        parameters: list[ParameterDSL],
        report_type: ReportType,
        requirement_summary: dict[str, Any],
        analysis: ExcelAnalysisResult | None,
        table_samples: dict[str, list[dict[str, Any]]],
        iteration: int,
    ) -> str | None:
        result = await _invoke_json_agent(
            system_prompt=(
                "你是 ReAct 风格的 SQL Server 报表 SQL Agent。"
                "你需要观察 Excel 模板意图、真实表结构、样例数据和上一次 SQL 执行结果，然后修正 SQL。"
                "目标是生成适配 FineReport 设计器的数据集。"
                "如果 Excel 模板中的城市、市场、区域适合通过 FineReport 横向扩展实现，应保持长表 SQL，不要用 CASE WHEN/PIVOT/SUM 强行转宽表。"
                "只能输出 SQL Server/T-SQL 的 SELECT 或 WITH 查询，不允许 DDL/DML/存储过程/多语句。"
                "只能使用 dataModel 中存在的表和字段；报表参数必须保留 ${parameterName} 占位符。"
                "只能使用 parameters 列表中已经定义的参数，不允许新增 ${market}、${product}、${grade} 等占位符。"
                "输出严格 JSON：thought、sql。"
            ),
            payload={
                "iteration": iteration,
                "requirementSummary": requirement_summary,
                "excelAnalysis": _compact_analysis(analysis),
                "dataModel": data_model.model_dump(mode="json"),
                "parameters": [item.model_dump(mode="json") for item in parameters],
                "reportType": report_type.value,
                "tableSamples": table_samples,
                "previousSql": sql,
                "validation": validation.model_dump(mode="json"),
                "guidance": [
                    "如果 Excel 模板出现地区横向列，而数据库是 record_date + market/area + price/value 长表，优先 SELECT record_date、market、price、change_amt 等原表字段，让 ReportDSL/FineReport 横向扩展。",
                    "只有源表本身已经是宽表，或用户明确要求固定列导出时，才考虑 CASE WHEN/PIVOT。",
                    "如果 Excel 有年份、日期、周次等行维度，优先从日期字段派生 YEAR、日期展示和 DATEPART(ISO_WEEK)。",
                    "生成的列名应稳定映射到真实字段，方便 ReportDSL 布局映射；不要臆造城市字段。",
                ],
            },
            agent_name="SqlReActAgent",
        )
        if not result:
            return None
        candidate = str(result.get("sql") or "").strip()
        return candidate if sql_agent._is_safe_sql(candidate, parameters) else None

    def _log_iteration(self, iteration: int, validation: SqlValidationResult) -> str:
        status = "通过" if validation.success else "失败"
        detail = "；".join(validation.errors or validation.warnings or [])
        return f"SQL ReAct 第 {iteration} 轮校验{status}" + (f"：{detail}" if detail else "")

    def _apply_template_expectation(
        self,
        validation: SqlValidationResult,
        analysis: ExcelAnalysisResult | None,
    ) -> None:
        if not validation.success or not analysis or not analysis.sheets:
            return
        template = self._primary_template(analysis)
        if not template:
            return

        horizontal_expansion = template.get("horizontalExpansion") or {}
        if horizontal_expansion.get("enabled") and horizontal_expansion.get("sqlShape") == "long_table_preferred":
            expected_long_fields = ["market", "area", "city", "price", "value"]
            actual_columns = {column.lower() for column in validation.columns}
            if any(expected in actual for expected in expected_long_fields for actual in actual_columns):
                validation.warnings.append("Excel 横向表头将由 FineReport 横向扩展处理，SQL 保持长表结果")
                return

        expected_columns = [
            str(item)
            for item in template.get("columnGroupLabels", [])
            if str(item).strip() and str(item) not in {"字段", "日期", "年份", "市场", "地区"}
        ][:12]
        if len(expected_columns) < 2:
            return

        actual_columns = {column.lower() for column in validation.columns}
        matched = [
            expected
            for expected in expected_columns
            if any(expected.lower() in actual or actual in expected.lower() for actual in actual_columns)
        ]
        if len(matched) >= min(2, len(expected_columns)):
            return

        validation.success = False
        validation.errors.append(
            "SQL 已执行但返回列未匹配 Excel 模板横向表头："
            + "、".join(expected_columns[:8])
            + "。如果该模板应使用 FineReport 横向扩展，请确保 SQL 至少返回市场/地区维度和价格/涨跌指标字段。"
        )

    def _primary_template(self, analysis: ExcelAnalysisResult) -> dict[str, Any] | None:
        sheet = next(
            (item for item in analysis.sheets if item.sheetName == analysis.primarySheet),
            analysis.sheets[0] if analysis.sheets else None,
        )
        return sheet.templateAnalysis if sheet else None


sql_react_agent = SqlReActAgent()
