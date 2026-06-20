from typing import Any

from app.schemas.agent.fr_report.ai_report import (
    ExcelAnalysisResult,
    FrAiReportMaintenanceField,
    FrAiReportMaintenanceTable,
    FrAiReportQualityGate,
    FrAiReportRequirementReviewResponse,
    FrAiReportWriteBackPlan,
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
        if self._is_options_ledger(text):
            return self._options_ledger_review(text, analysis, source_table_name, table_schema)
        if self._is_futures_ledger(text):
            return self._futures_ledger_review(text, analysis, source_table_name, table_schema)
        return self._generic_review(text, analysis, source_table_name, table_schema)

    def _options_ledger_review(
        self,
        text: str,
        analysis: ExcelAnalysisResult | None,
        source_table_name: str | None,
        table_schema: dict[str, Any] | None,
    ) -> FrAiReportRequirementReviewResponse:
        has_source = bool(source_table_name or table_schema)
        return FrAiReportRequirementReviewResponse(
            status="needs_confirmation" if not has_source else "ready",
            scenario="option_operation_ledger",
            summary="场内期权操作台账填报表，同一行记录项目、开仓、平仓、收益情况、持仓量和备注。",
            reportType="detail_table",
            extractedRequirements=self._extract_requirement_lines(text),
            questions=[
                "是否已经存在场内期权台账和期权合约基础资料表？如果有，请提供真实表名和字段。",
                "合约乘数是否统一为 10，还是需要按品种合约、标的合约、期权类型和执行价维护？",
                "收益情况是否固定按“(平仓权利金单价 - 开仓权利金单价) * 开仓成交量 * 合约乘数 - 开仓手续费 - 平仓手续费”计算？",
                "持仓量是人工录入、按开仓和平仓成交量自动计算，还是从外部持仓表读取？",
            ],
            assumptions=[
                "品种合约、标的合约、期权类型、执行价、买/卖和合约乘数使用独立基础资料表维护。",
                "同一行录入的开仓和平仓天然对应，收益情况为只读计算字段。",
                "新增行使用隐藏 ledger_id 自动生成主键，支持行内插入和删除。",
                "首版单元格控件采用文本、数字和日期轻量控件，不绑定大数据集下拉，避免填报预览卡顿。",
            ],
            maintenanceTables=self._options_tables(),
            recommendedSourceTables=[
                "fr_option_contract_base",
                "fr_option_trade_ledger",
            ],
            qualityGates=[
                FrAiReportQualityGate(
                    code="option_contract_base_required",
                    label="期权合约基础资料完整",
                    severity="error",
                    description="品种合约、标的合约、期权类型、执行价、买/卖和合约乘数必须能从维护表取得。",
                    autoCheck=True,
                ),
                FrAiReportQualityGate(
                    code="option_profit_formula_confirmed",
                    label="收益计算公式已确认",
                    severity="error",
                    description="收益情况必须使用已确认的权利金、成交量、合约乘数和手续费口径计算，不能作为人工录入字段。",
                    autoCheck=True,
                ),
                FrAiReportQualityGate(
                    code="option_open_close_same_row",
                    label="开仓平仓同一行对应",
                    severity="error",
                    description="同一行的开仓和平仓信息作为一组业务记录写回，删除行需要同步删除整条台账记录。",
                    autoCheck=True,
                ),
            ],
            writeBackPlan=FrAiReportWriteBackPlan(
                enabled=True,
                mode="update",
                targetTable="fr_option_trade_ledger",
                primaryKeys=["id"],
                hiddenKeys=["id"],
                editableFields=[
                    "variety_contract",
                    "underlying_contract",
                    "option_type",
                    "strike_price",
                    "trade_side",
                    "open_date",
                    "open_premium_price",
                    "open_volume",
                    "open_fee",
                    "close_date",
                    "close_premium_price",
                    "close_volume",
                    "close_fee",
                    "position_volume",
                    "remark",
                ],
                calculatedFields=["realized_profit"],
                allowInsert=True,
                allowDelete=True,
                safetyNotes=[
                    "新增行使用隐藏 id 自动生成主键；是否自增由建表选项决定。",
                    "收益情况保持只读，由 SQL 或单元格公式计算。",
                    "合约乘数默认按基础资料表读取，未维护时按 10 的业务假设处理。",
                    "单元格不使用大数据集下拉控件，避免填报预览卡顿。",
                ],
            ),
            warnings=[] if has_source else ["当前未提供真实业务表名，已先按生产建议生成期权台账数据模型草案，正式生成前需要确认表结构。"],
            excelAnalysis=analysis,
        )

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
                "当前生成结果可以直接生成填报预览；正式发布前仍应确认写回表、主键和权限。",
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
            writeBackPlan=FrAiReportWriteBackPlan(
                enabled=True,
                mode="update",
                targetTable="fr_future_trade_ledger",
                primaryKeys=["ledger_id"],
                hiddenKeys=["ledger_id"],
                editableFields=[
                    "account_name",
                    "contract_variety",
                    "contract_code",
                    "strategy_type",
                    "operation_unit",
                    "open_date",
                    "open_direction",
                    "open_quantity_lot",
                    "open_price",
                    "open_fee_per_lot",
                    "close_date",
                    "close_direction",
                    "close_quantity_lot",
                    "close_price",
                    "close_fee_per_lot",
                ],
                calculatedFields=[
                    "realized_profit",
                    "position_direction",
                    "remaining_quantity_lot",
                    "settlement_price",
                    "floating_profit",
                ],
                allowInsert=True,
                allowDelete=True,
                safetyNotes=[
                    "新增行使用隐藏 ledger_id 自动生成主键。",
                    "平仓数量不得超过开仓数量。",
                    "单元格不使用大数据集下拉控件，避免填报预览卡顿。",
                ],
            ),
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
        needs_writeback = self._needs_writeback(text)
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
        if needs_writeback:
            questions.extend(
                [
                    "请确认填报写回的目标表，以及是否允许新增行、删除行。",
                    "请确认主键字段；如果没有稳定主键，建议增加隐藏主键字段，例如 row_id 或 ledger_id。",
                    "请确认哪些字段允许录入，哪些字段只读或由公式/SQL 自动计算。",
                ]
            )
        editable_fields = self._editable_fields_from_analysis(analysis)
        primary_keys = self._candidate_primary_keys(editable_fields)
        source_tables = self._parse_table_names(source_table_name)
        return FrAiReportRequirementReviewResponse(
            status="needs_confirmation" if questions else "ready",
            scenario="generic_report",
            summary=text[:120] or "通用表格报表需求。",
            extractedRequirements=self._extract_requirement_lines(text),
            questions=questions,
            assumptions=[],
            maintenanceTables=tables,
            recommendedSourceTables=source_tables,
            qualityGates=self._generic_writeback_quality_gates() if needs_writeback else [],
            writeBackPlan=FrAiReportWriteBackPlan(
                enabled=needs_writeback,
                mode="update" if needs_writeback else "none",
                targetTable=(source_tables or [None])[0],
                primaryKeys=primary_keys,
                hiddenKeys=[key for key in primary_keys if key.endswith("_id") or key == "id"],
                editableFields=editable_fields,
                allowInsert=any(keyword in text for keyword in ["新增", "插入", "添加", "增行", "添加记录"]),
                allowDelete=any(keyword in text for keyword in ["删除", "删行", "删除记录"]),
                safetyNotes=[
                    "未确认主键时不得自动发布到正式目录。",
                    "单元格下拉只允许绑定小字典表，不默认绑定主数据集。",
                    "提交前需要在 FineReport 写入模式下预览验证。",
                ] if needs_writeback else [],
            ),
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

    def _options_tables(self) -> list[FrAiReportMaintenanceTable]:
        return [
            FrAiReportMaintenanceTable(
                tableName="fr_option_contract_base",
                displayName="期权合约基础资料",
                purpose="维护品种合约、标的合约、期权类型、执行价、买/卖和合约乘数，为填报字段和收益计算提供基础资料。",
                fields=[
                    FrAiReportMaintenanceField(name="option_contract_id", label="期权合约ID"),
                    FrAiReportMaintenanceField(name="variety_contract", label="品种合约"),
                    FrAiReportMaintenanceField(name="underlying_contract", label="标的合约"),
                    FrAiReportMaintenanceField(name="option_type", label="期权类型"),
                    FrAiReportMaintenanceField(name="strike_price", label="执行价", type="decimal"),
                    FrAiReportMaintenanceField(name="trade_side", label="买/卖"),
                    FrAiReportMaintenanceField(name="contract_multiplier", label="合约乘数", type="decimal"),
                    FrAiReportMaintenanceField(name="status", label="状态"),
                ],
                keys=["option_contract_id"],
                uniqueKeys=[["variety_contract", "underlying_contract", "option_type", "strike_price", "trade_side"]],
                dropdownTargets=["品种合约", "标的合约", "期权类型", "执行价", "买/卖"],
            ),
            FrAiReportMaintenanceTable(
                tableName="fr_option_trade_ledger",
                displayName="场内期权操作台账",
                purpose="同一行记录期权开仓、平仓、收益情况、持仓量和备注，作为填报主表。",
                fields=[
                    FrAiReportMaintenanceField(name="id", label="主键ID"),
                    FrAiReportMaintenanceField(name="variety_contract", label="品种合约"),
                    FrAiReportMaintenanceField(name="underlying_contract", label="标的合约"),
                    FrAiReportMaintenanceField(name="option_type", label="期权类型"),
                    FrAiReportMaintenanceField(name="strike_price", label="执行价", type="decimal"),
                    FrAiReportMaintenanceField(name="trade_side", label="买/卖"),
                    FrAiReportMaintenanceField(name="open_date", label="开仓日期", type="date"),
                    FrAiReportMaintenanceField(name="open_premium_price", label="开仓权利金单价", type="decimal"),
                    FrAiReportMaintenanceField(name="open_volume", label="开仓成交量", type="decimal"),
                    FrAiReportMaintenanceField(name="open_fee", label="开仓手续费", type="decimal"),
                    FrAiReportMaintenanceField(name="close_date", label="平仓日期", type="date", required=False),
                    FrAiReportMaintenanceField(name="close_premium_price", label="平仓权利金单价", type="decimal", required=False),
                    FrAiReportMaintenanceField(name="close_volume", label="平仓成交量", type="decimal", required=False),
                    FrAiReportMaintenanceField(name="close_fee", label="平仓手续费", type="decimal", required=False),
                    FrAiReportMaintenanceField(name="position_volume", label="持仓量", type="decimal", required=False),
                    FrAiReportMaintenanceField(name="remark", label="备注", required=False),
                ],
                keys=["id"],
                uniqueKeys=[["id"]],
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
        keywords = ["期货", "合约", "开仓", "平仓", "持仓", "吨数/手", "浮动盈亏"]
        return sum(1 for keyword in keywords if keyword in text) >= 3

    def _is_options_ledger(self, text: str) -> bool:
        option_keywords = ["期权", "场内期权", "权利金", "执行价", "标的合约"]
        ledger_keywords = ["开仓", "平仓", "持仓", "填报", "台账"]
        return any(keyword in text for keyword in option_keywords) and sum(1 for keyword in ledger_keywords if keyword in text) >= 2

    def _needs_writeback(self, text: str) -> bool:
        return any(keyword in text for keyword in ["填报", "录入", "写回", "提交", "维护", "新增", "删除", "插入行", "删除行"])

    def _editable_fields_from_analysis(self, analysis: ExcelAnalysisResult | None) -> list[str]:
        if not analysis or not analysis.sheets:
            return []
        fields = []
        for field in analysis.sheets[0].fields:
            label = f"{field.name} {field.label}"
            if any(keyword in label for keyword in ["盈亏", "合计", "剩余", "浮动", "完成率", "进度"]):
                continue
            fields.append(field.name)
        return fields[:30]

    def _candidate_primary_keys(self, field_names: list[str]) -> list[str]:
        preferred = [field for field in field_names if field in {"id", "row_id", "ledger_id"} or field.endswith("_id")]
        return preferred[:1] or field_names[:1]

    def _generic_writeback_quality_gates(self) -> list[FrAiReportQualityGate]:
        return [
            FrAiReportQualityGate(
                code="writeback_primary_key_required",
                label="填报主键已确认",
                severity="error",
                description="填报写回必须存在稳定主键；无主键时应新增隐藏主键字段。",
                autoCheck=True,
            ),
            FrAiReportQualityGate(
                code="writeback_fields_confirmed",
                label="可编辑字段已确认",
                severity="error",
                description="AI 只能让已确认可录入的字段生成控件，计算字段保持只读。",
                autoCheck=True,
            ),
            FrAiReportQualityGate(
                code="writeback_preview_mode",
                label="填报预览模式校验",
                severity="warning",
                description="生成 CPT 后必须使用 op=write 预览地址验证控件、按钮和提交工具栏。",
                autoCheck=True,
            ),
        ]

    def _parse_table_names(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.replace("，", ",").replace("；", ",").split(",") if item.strip()][:8]


fr_report_requirement_planner = FrReportRequirementPlanner()
