from typing import Any

from app.schemas.agent.fr_report.ai_report import (
    ExcelAnalysisResult,
    FrAiReportMaintenanceField,
    FrAiReportMaintenanceTable,
    FrAiReportQualityGate,
    FrAiReportRequirementReviewResponse,
)


class FrReportRequirementPlanner:
    def review(
        self,
        requirement: str | None,
        analysis: ExcelAnalysisResult | None,
        source_table_name: str | None = None,
        table_schema: dict[str, Any] | None = None,
    ) -> FrAiReportRequirementReviewResponse:
        text = self._combined_text(requirement, analysis)
        if self._is_futures_ledger(text):
            return self._futures_ledger_review(text, analysis, source_table_name, table_schema)
        return self._generic_review(text, analysis, source_table_name, table_schema)

    def _futures_ledger_review(
        self,
        text: str,
        analysis: ExcelAnalysisResult | None,
        source_table_name: str | None,
        table_schema: dict[str, Any] | None,
    ) -> FrAiReportRequirementReviewResponse:
        has_source = bool(source_table_name or table_schema)
        return FrAiReportRequirementReviewResponse(
            status="needs_confirmation" if not has_source else "ready",
            scenario="futures_operation_ledger",
            summary="期货/期权操作台账，包含查询台账、独立录入、开仓、平仓、持仓、每日结算价和盈亏计算。",
            reportType="detail_table",
            extractedRequirements=self._extract_requirement_lines(text),
            questions=[
                "是否已经存在期货操作台账、合约基础资料、每日收盘价这些数据库表？如果有，请提供真实表名和字段。",
                "吨数/手是按合约代码维护，还是按合约品种维护？是否存在生效日期或历史版本？",
                "策略类型有哪些固定选项？例如套保、投机，是否还包含套利等类型？",
                "手续费是否开仓和平仓都按元/手计算？是否需要支持按金额或按比例收费？",
                "查询截止日没有维护收盘价时，浮动盈亏是置空、取最近一天，还是提示缺失？",
            ],
            assumptions=[
                "账户名称、合约品种、合约代码、吨数/手、操作单位需要单独维护基础表，并作为下拉框来源。",
                "查询界面只读，录入界面单独设计为填报表。",
                "同一行录入的开仓和平仓天然对应，平仓数量不能超过本行开仓数量。",
                "浮动盈亏按查询截止日期的收盘价计算。",
            ],
            maintenanceTables=self._futures_tables(),
            recommendedSourceTables=[
                "fr_future_contract_base",
                "fr_future_trade_ledger",
                "fr_future_settlement_price",
            ],
            qualityGates=[
                FrAiReportQualityGate(
                    code="contract_base_required",
                    label="合约基础资料完整",
                    severity="error",
                    description="账户名称、合约品种、合约代码、吨数/手、操作单位必须能从维护表取得。",
                    autoCheck=True,
                ),
                FrAiReportQualityGate(
                    code="close_qty_not_exceed_position",
                    label="平仓数量不超过本行开仓数量",
                    severity="error",
                    description="同一行录入开仓和平仓时，平仓数量必须小于等于本行开仓数量。",
                    autoCheck=True,
                ),
                FrAiReportQualityGate(
                    code="settlement_price_for_float_profit",
                    label="浮盈收盘价可匹配",
                    severity="warning",
                    description="有持仓的合约在查询截止日应维护收盘价，否则浮动盈亏无法准确计算。",
                    autoCheck=True,
                ),
                FrAiReportQualityGate(
                    code="readonly_query_writeback_separation",
                    label="查询和录入分离",
                    severity="error",
                    description="台账查询页必须只读，开仓、平仓和结算价维护应进入独立填报页。",
                    autoCheck=False,
                ),
            ],
            warnings=[] if has_source else ["当前未提供真实业务表名，已先按生产建议生成数据模型草案，正式生成前需要确认表结构。"],
            excelAnalysis=analysis,
        )

    def _generic_review(
        self,
        text: str,
        analysis: ExcelAnalysisResult | None,
        source_table_name: str | None,
        table_schema: dict[str, Any] | None,
    ) -> FrAiReportRequirementReviewResponse:
        needs_maintenance = any(keyword in text for keyword in ["维护", "下拉", "录入", "填报", "基础表", "主数据"])
        questions = []
        tables: list[FrAiReportMaintenanceTable] = []
        if needs_maintenance:
            questions.append("哪些字段需要作为下拉框或基础资料维护？请确认字段名、唯一性和是否允许停用。")
            tables.append(
                FrAiReportMaintenanceTable(
                    tableName="fr_report_master_data",
                    displayName="报表基础资料维护表",
                    purpose="维护报表下拉框和基础资料，供查询和填报界面引用。",
                    fields=[
                        FrAiReportMaintenanceField(name="category", label="资料类别"),
                        FrAiReportMaintenanceField(name="code", label="编码"),
                        FrAiReportMaintenanceField(name="name", label="名称"),
                        FrAiReportMaintenanceField(name="status", label="状态"),
                    ],
                    keys=["category", "code"],
                    uniqueKeys=[["category", "code"]],
                )
            )
        return FrAiReportRequirementReviewResponse(
            status="needs_confirmation" if questions else "ready",
            scenario="generic_report",
            summary=text[:120] or "通用表格报表需求。",
            extractedRequirements=self._extract_requirement_lines(text),
            questions=questions,
            assumptions=[],
            maintenanceTables=tables,
            recommendedSourceTables=self._parse_table_names(source_table_name),
            qualityGates=[],
            warnings=[] if (source_table_name or table_schema) else ["当前未提供真实业务表名，SQL 生成可能只能形成草案。"],
            excelAnalysis=analysis,
        )

    def _futures_tables(self) -> list[FrAiReportMaintenanceTable]:
        return [
            FrAiReportMaintenanceTable(
                tableName="fr_future_contract_base",
                displayName="期货合约基础资料",
                purpose="维护账户名称、合约品种、合约代码、吨数/手和操作单位，账户名称 + 合约品种 + 合约代码作为组合主键，为查询筛选与填报下拉框提供来源。",
                fields=[
                    FrAiReportMaintenanceField(name="account_name", label="账户名称"),
                    FrAiReportMaintenanceField(name="contract_variety", label="合约品种"),
                    FrAiReportMaintenanceField(name="contract_code", label="合约代码"),
                    FrAiReportMaintenanceField(name="tons_per_lot", label="吨数/手", type="decimal"),
                    FrAiReportMaintenanceField(name="operation_unit", label="操作单位"),
                    FrAiReportMaintenanceField(name="status", label="状态"),
                ],
                keys=["account_name", "contract_variety", "contract_code"],
                uniqueKeys=[["account_name", "contract_variety", "contract_code"]],
                dropdownTargets=["账户名称", "合约品种", "合约代码", "操作单位"],
            ),
            FrAiReportMaintenanceTable(
                tableName="fr_future_trade_ledger",
                displayName="期货操作台账",
                purpose="同一行记录开仓、平仓和持仓相关信息，作为只读查询台账和录入界面的主表。",
                fields=[
                    FrAiReportMaintenanceField(name="ledger_id", label="台账单号"),
                    FrAiReportMaintenanceField(name="account_name", label="账户名称"),
                    FrAiReportMaintenanceField(name="contract_variety", label="合约品种"),
                    FrAiReportMaintenanceField(name="contract_code", label="合约代码"),
                    FrAiReportMaintenanceField(name="strategy_type", label="策略类型"),
                    FrAiReportMaintenanceField(name="operation_unit", label="操作单位"),
                    FrAiReportMaintenanceField(name="open_date", label="开仓日期", type="date"),
                    FrAiReportMaintenanceField(name="open_direction", label="开仓方向"),
                    FrAiReportMaintenanceField(name="open_quantity_lot", label="开仓数量（手）", type="decimal"),
                    FrAiReportMaintenanceField(name="open_price", label="开仓价格（元/吨）", type="decimal"),
                    FrAiReportMaintenanceField(name="close_date", label="平仓日期", type="date"),
                    FrAiReportMaintenanceField(name="close_direction", label="平仓方向"),
                    FrAiReportMaintenanceField(name="close_quantity_lot", label="平仓数量（手）", type="decimal"),
                    FrAiReportMaintenanceField(name="close_price", label="平仓价格（元/吨）", type="decimal"),
                    FrAiReportMaintenanceField(name="open_fee_per_lot", label="开仓手续费（元/手）", type="decimal"),
                    FrAiReportMaintenanceField(name="close_fee_per_lot", label="平仓手续费（元/手）", type="decimal"),
                ],
                keys=["ledger_id"],
                uniqueKeys=[["ledger_id"]],
            ),
            FrAiReportMaintenanceTable(
                tableName="fr_future_settlement_price",
                displayName="期货每日收盘价维护",
                purpose="维护查询截止日的合约收盘价，用于计算持仓浮动盈亏。",
                fields=[
                    FrAiReportMaintenanceField(name="price_date", label="价格日期", type="date"),
                    FrAiReportMaintenanceField(name="contract_code", label="合约代码"),
                    FrAiReportMaintenanceField(name="settlement_price", label="收盘价（元/吨）", type="decimal"),
                ],
                keys=["price_date", "contract_code"],
                uniqueKeys=[["price_date", "contract_code"]],
                dropdownTargets=["合约代码"],
            ),
        ]

    def _combined_text(self, requirement: str | None, analysis: ExcelAnalysisResult | None) -> str:
        parts = [requirement or ""]
        for sheet in (analysis.sheets if analysis else []):
            template = sheet.templateAnalysis or {}
            for row in template.get("notes") or []:
                parts.append(str(row))
            for row in template.get("requirementLines") or []:
                parts.append(str(row))
            parts.extend(str(field.label) for field in sheet.fields)
            for sample in sheet.sampleRows[:5]:
                parts.extend(str(value) for value in sample.values() if value not in (None, ""))
        return "\n".join(part for part in parts if part).strip()

    def _extract_requirement_lines(self, text: str) -> list[str]:
        lines = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith(("1", "2", "3", "4", "5", "（", "需求")) or any(
                keyword in line for keyword in ["查询", "录入", "平仓", "持仓", "维护", "自动计算", "换算率"]
            ):
                lines.append(line)
        return list(dict.fromkeys(lines))[:12]

    def _is_futures_ledger(self, text: str) -> bool:
        keywords = ["期货", "期权", "合约", "开仓", "平仓", "持仓", "吨数/手", "浮动盈亏"]
        return sum(1 for keyword in keywords if keyword in text) >= 3

    def _parse_table_names(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.replace("，", ",").replace("；", ",").split(",") if item.strip()][:8]


fr_report_requirement_planner = FrReportRequirementPlanner()
