import asyncio
import json
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.core.llm_factory import LLMFactory
from app.core.logger import logger
from app.schemas.agent.weaver_ai_assistant import WeaverReviewRequest, WeaverReviewRuleRead
from app.services.agent.weaver_ai_assistant.assistant_service import weaver_ai_assistant_service


class WeaverReviewEvidenceService:
    """执行智审规则声明的只读证据工具。"""

    TOOL_TYPE = "weaver_reconciliation_invoice_match"
    IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    UNIT_CONVERSIONS: dict[str, tuple[str, Decimal]] = {
        "t": ("mass", Decimal("1000")),
        "kg": ("mass", Decimal("1")),
        "g": ("mass", Decimal("0.001")),
        "mg": ("mass", Decimal("0.000001")),
        "m3": ("volume", Decimal("1000")),
        "l": ("volume", Decimal("1")),
        "ml": ("volume", Decimal("0.001")),
        "m": ("length", Decimal("1")),
        "cm": ("length", Decimal("0.01")),
        "mm": ("length", Decimal("0.001")),
    }

    async def collect(
        self,
        payload: WeaverReviewRequest,
        rules: list[WeaverReviewRuleRead],
    ) -> list[dict[str, Any]]:
        tools = self._enabled_tools(rules)
        if not tools:
            return []

        evidence: list[dict[str, Any]] = []
        for tool in tools:
            if tool.get("type") != self.TOOL_TYPE:
                continue
            try:
                result = await self._run_reconciliation_invoice_match(payload, tool)
            except Exception as exc:
                logger.exception(f"泛微智审证据工具执行失败: type={self.TOOL_TYPE}, error={exc}")
                result = {
                    "toolType": self.TOOL_TYPE,
                    "status": "warning",
                    "summary": "采购对账单与发票明细核验暂时不可用，需人工复核。",
                    "checks": [
                        {
                            "name": "关联数据核验",
                            "status": "warning",
                            "detail": "关联数据读取失败，系统未据此作出通过判断。",
                        }
                    ],
                    "concerns": ["采购对账单与发票明细未完成系统核验"],
                }
            evidence.append(result)
        return evidence

    async def _run_reconciliation_invoice_match(
        self,
        payload: WeaverReviewRequest,
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        prepared = await asyncio.to_thread(
            self._load_reconciliation_invoice_data,
            payload,
            tool,
        )
        if "result" in prepared:
            return prepared["result"]
        return await self._compare(**prepared)

    def _load_reconciliation_invoice_data(
        self,
        payload: WeaverReviewRequest,
        tool: dict[str, Any],
    ) -> dict[str, Any]:
        env = weaver_ai_assistant_service._normalize_env(payload.context.env or "default")
        custom_id = self._positive_int(tool.get("customId"), "建模查询 ID")
        amount_tolerance = self._decimal(tool.get("amountTolerance"), Decimal("0.10"))
        similarity_threshold = self._bounded_float(tool.get("nameSimilarityThreshold"), 0.78)
        semantic_confidence_threshold = self._bounded_float(
            tool.get("semanticConfidenceThreshold"),
            0.72,
        )
        reconciliation_labels = tool.get("reconciliationFieldLabels") or ["对账单号主表", "对账单号", "对账单信息"]
        invoice_labels = tool.get("invoiceFieldLabels") or ["发票号码", "发票信息"]
        reconciliation_number = self._find_context_value(
            payload,
            reconciliation_labels,
            prefer_text=True,
        )
        invoice_refs = self._find_context_values(
            payload,
            invoice_labels,
        )

        db_config = weaver_ai_assistant_service._get_weaver_db_config(env)
        conn = weaver_ai_assistant_service._connect_weaver_mysql(db_config)
        try:
            with conn.cursor() as cursor:
                reference_source = "ecode 页面上下文"
                if not reconciliation_number or not invoice_refs:
                    database_references = self._fetch_workflow_references(
                        cursor,
                        workflow_id=self._workflow_id(payload),
                        request_id=self._request_id(payload),
                        reconciliation_labels=reconciliation_labels,
                        invoice_labels=invoice_labels,
                    )
                    reconciliation_number = reconciliation_number or self._prefer_text_value(
                        database_references["reconciliationNumbers"]
                    )
                    invoice_refs = list(dict.fromkeys(invoice_refs + database_references["invoiceReferences"]))
                    reference_source = "泛微流程表单数据库"
                if not reconciliation_number:
                    return {"result": self._missing_evidence("未从当前流程表单及流程数据库读取到对账单号。")}
                if not invoice_refs:
                    return {"result": self._missing_evidence("未从当前流程表单及流程数据库读取到发票号码或发票浏览框记录。")}

                metadata = self._resolve_reconciliation_metadata(cursor, custom_id)
                reconciliation = self._fetch_reconciliation(
                    cursor,
                    metadata,
                    reconciliation_number,
                )
                invoices = self._fetch_invoices(cursor, invoice_refs)
        finally:
            conn.close()

        return {
            "reconciliation_number": reconciliation_number,
            "reconciliation": reconciliation,
            "invoices": invoices,
            "amount_tolerance": amount_tolerance,
            "similarity_threshold": similarity_threshold,
            "semantic_confidence_threshold": semantic_confidence_threshold,
            "reference_source": reference_source,
        }

    def _fetch_workflow_references(
        self,
        cursor: Any,
        *,
        workflow_id: str,
        request_id: str,
        reconciliation_labels: list[Any],
        invoice_labels: list[Any],
    ) -> dict[str, list[str]]:
        if not workflow_id or not request_id:
            return {"reconciliationNumbers": [], "invoiceReferences": []}

        cursor.execute(
            """
            SELECT w.FORMID, b.TABLENAME, b.DETAILKEYFIELD
            FROM workflow_base w
            JOIN workflow_bill b ON b.ID = w.FORMID
            WHERE w.ID = %s
            """,
            (workflow_id,),
        )
        form = self._normalize_row(cursor.fetchone())
        if not form:
            return {"reconciliationNumbers": [], "invoiceReferences": []}

        cursor.execute(
            """
            SELECT f.FIELDNAME, f.DETAILTABLE, l.LABELNAME
            FROM workflow_billfield f
            LEFT JOIN htmllabelinfo l ON l.INDEXID = f.FIELDLABEL AND l.LANGUAGEID = 7
            WHERE f.BILLID = %s
            ORDER BY f.DETAILTABLE, f.DSPORDER, f.ID
            """,
            (form["formid"],),
        )
        fields = [self._normalize_row(row) for row in cursor.fetchall()]
        expected_reconciliation = {self._normalize_label(item) for item in reconciliation_labels if self._text(item)}
        expected_invoice = {self._normalize_label(item) for item in invoice_labels if self._text(item)}
        selected_fields = [
            field
            for field in fields
            if self._label_matches(field.get("labelname"), expected_reconciliation | expected_invoice)
        ]
        if not selected_fields:
            return {"reconciliationNumbers": [], "invoiceReferences": []}

        main_table = self._identifier(form["tablename"])
        main_columns = [self._identifier(field["fieldname"]) for field in selected_fields if not field.get("detailtable")]
        main_row: dict[str, Any] = {}
        if main_columns:
            select_columns = ", ".join(["`id`", *[f"`{column}`" for column in dict.fromkeys(main_columns)]])
            cursor.execute(
                f"SELECT {select_columns} FROM `{main_table}` WHERE `requestid` = %s ORDER BY id DESC LIMIT 1",
                (request_id,),
            )
            main_row = self._normalize_row(cursor.fetchone())

        reconciliation_values: list[str] = []
        invoice_values: list[str] = []
        self._collect_reference_values(
            selected_fields,
            main_row,
            expected_reconciliation,
            expected_invoice,
            reconciliation_values,
            invoice_values,
            detail_table="",
        )

        main_id = main_row.get("id")
        detail_key = self._identifier(form.get("detailkeyfield") or "mainid")
        detail_tables = sorted({self._identifier(field["detailtable"]) for field in selected_fields if field.get("detailtable")})
        for detail_table in detail_tables:
            if main_id is None:
                cursor.execute(f"SELECT `id` FROM `{main_table}` WHERE `requestid` = %s ORDER BY id DESC LIMIT 1", (request_id,))
                main_id_row = self._normalize_row(cursor.fetchone())
                main_id = main_id_row.get("id")
            if main_id is None:
                continue
            detail_columns = [
                self._identifier(field["fieldname"])
                for field in selected_fields
                if self._text(field.get("detailtable")).lower() == detail_table.lower()
            ]
            select_columns = ", ".join(f"`{column}`" for column in dict.fromkeys(detail_columns))
            cursor.execute(
                f"SELECT {select_columns} FROM `{detail_table}` WHERE `{detail_key}` = %s ORDER BY id LIMIT 500",
                (main_id,),
            )
            for row in cursor.fetchall():
                self._collect_reference_values(
                    selected_fields,
                    self._normalize_row(row),
                    expected_reconciliation,
                    expected_invoice,
                    reconciliation_values,
                    invoice_values,
                    detail_table=detail_table,
                )

        logger.info(
            "泛微智审从流程数据库补充关联字段: "
            f"workflow_id={workflow_id}, request_id={request_id}, "
            f"reconciliation_count={len(reconciliation_values)}, invoice_count={len(invoice_values)}"
        )
        return {
            "reconciliationNumbers": list(dict.fromkeys(reconciliation_values)),
            "invoiceReferences": list(dict.fromkeys(invoice_values)),
        }

    def _collect_reference_values(
        self,
        fields: list[dict[str, Any]],
        row: dict[str, Any],
        reconciliation_labels: set[str],
        invoice_labels: set[str],
        reconciliation_values: list[str],
        invoice_values: list[str],
        *,
        detail_table: str,
    ) -> None:
        for field in fields:
            field_detail_table = self._text(field.get("detailtable"))
            if field_detail_table.lower() != detail_table.lower():
                continue
            values = self._flatten_values(row.get(self._text(field.get("fieldname")).lower()))
            if self._label_matches(field.get("labelname"), reconciliation_labels):
                reconciliation_values.extend(value for value in values if value not in reconciliation_values)
            if self._label_matches(field.get("labelname"), invoice_labels):
                invoice_values.extend(value for value in values if value not in invoice_values)

    def _label_matches(self, value: Any, expected: set[str]) -> bool:
        label = self._normalize_label(value)
        return bool(label and any(item in label or label in item for item in expected))

    def _prefer_text_value(self, values: list[str]) -> str:
        return next((value for value in values if not value.isdigit()), values[0] if values else "")

    def _workflow_id(self, payload: WeaverReviewRequest) -> str:
        return self._text(payload.context.base_info.get("workflowid") or payload.context.base_info.get("workflowId"))

    def _request_id(self, payload: WeaverReviewRequest) -> str:
        return self._text(payload.context.base_info.get("requestid") or payload.context.base_info.get("requestId"))

    def _resolve_reconciliation_metadata(self, cursor: Any, custom_id: int) -> dict[str, Any]:
        cursor.execute(
            """
            SELECT c.ID, c.FORMID, c.CUSTOMNAME, b.TABLENAME, b.DETAILKEYFIELD
            FROM mode_customsearch c
            JOIN workflow_bill b ON b.ID = c.FORMID
            WHERE c.ID = %s
            """,
            (custom_id,),
        )
        custom_search = self._normalize_row(cursor.fetchone())
        if not custom_search:
            raise ValueError(f"未找到建模查询 customId={custom_id}")

        cursor.execute(
            """
            SELECT f.FIELDNAME, f.DETAILTABLE, l.LABELNAME
            FROM workflow_billfield f
            LEFT JOIN htmllabelinfo l ON l.INDEXID = f.FIELDLABEL AND l.LANGUAGEID = 7
            WHERE f.BILLID = %s
            ORDER BY f.DETAILTABLE, f.DSPORDER, f.ID
            """,
            (custom_search["formid"],),
        )
        fields = [self._normalize_row(row) for row in cursor.fetchall()]

        main_table = self._identifier(custom_search["tablename"])
        reconciliation_field = self._field_by_label(fields, ["对账单号"], detail=False)
        item_description = self._field_by_label(fields, ["采购物料描述", "物料描述", "物品名称"], detail=True)
        item_table = self._identifier(item_description["detailtable"])
        item_fields = {
            "description": self._identifier(item_description["fieldname"]),
            "code": self._optional_field(fields, item_table, ["采购物料编码", "物料编码"]),
            "specification": self._optional_field(fields, item_table, ["规格型号", "规格"]),
            "unit": self._optional_field(fields, item_table, ["计量单位", "单位"], field_names=["dw"]),
            "quantity": self._optional_field(fields, item_table, ["凭证数量", "数量"]),
            "untaxedAmount": self._optional_field(fields, item_table, ["未税金额", "不含税金额"]),
            "taxedAmount": self._optional_field(fields, item_table, ["含税金额"]),
            "taxRate": self._optional_field(fields, item_table, ["税率"]),
        }
        return {
            "customName": custom_search.get("customname") or "建模查询",
            "mainTable": main_table,
            "detailKeyField": self._identifier(custom_search.get("detailkeyfield") or "mainid"),
            "reconciliationField": self._identifier(reconciliation_field["fieldname"]),
            "itemTable": item_table,
            "itemFields": item_fields,
        }

    def _fetch_reconciliation(
        self,
        cursor: Any,
        metadata: dict[str, Any],
        reconciliation_number: str,
    ) -> dict[str, Any]:
        main_table = metadata["mainTable"]
        reconciliation_field = metadata["reconciliationField"]
        cursor.execute(
            f"SELECT * FROM `{main_table}` WHERE `{reconciliation_field}` = %s ORDER BY id DESC LIMIT 2",
            (reconciliation_number,),
        )
        headers = [self._normalize_row(row) for row in cursor.fetchall()]
        if not headers:
            return {"header": None, "items": [], "metadata": metadata}
        if len(headers) > 1:
            logger.warning(
                "泛微智审对账单号命中多条记录，默认使用最新记录: "
                f"reconciliation_number={reconciliation_number}, count={len(headers)}"
            )
        header = headers[0]
        item_fields = metadata["itemFields"]
        columns = ["id", metadata["detailKeyField"]] + [value for value in item_fields.values() if value]
        select_columns = ", ".join(f"`{column}`" for column in dict.fromkeys(columns))
        cursor.execute(
            f"SELECT {select_columns} FROM `{metadata['itemTable']}` "
            f"WHERE `{metadata['detailKeyField']}` = %s ORDER BY id LIMIT 500",
            (header["id"],),
        )
        return {
            "header": header,
            "items": [self._normalize_row(row) for row in cursor.fetchall()],
            "metadata": metadata,
        }

    def _fetch_invoices(self, cursor: Any, invoice_refs: list[str]) -> list[dict[str, Any]]:
        ids = sorted({int(value) for value in invoice_refs if str(value).isdigit()})
        numbers = sorted({str(value).strip() for value in invoice_refs if not str(value).isdigit()})
        conditions: list[str] = []
        params: list[Any] = []
        if ids:
            conditions.append(f"id IN ({','.join(['%s'] * len(ids))})")
            params.extend(ids)
        if numbers:
            conditions.append(f"invoiceNumber IN ({','.join(['%s'] * len(numbers))})")
            params.extend(numbers)
        if not conditions:
            return []
        cursor.execute(
            "SELECT id, invoiceNumber, invoiceCode, seller, purchaser, taxIncludedPrice, "
            "priceWithoutTax, tax, checkStatus, authenticity "
            f"FROM fnainvoiceledger WHERE {' OR '.join(conditions)} ORDER BY id",
            tuple(params),
        )
        invoices = [self._normalize_row(row) for row in cursor.fetchall()]
        for invoice in invoices:
            cursor.execute(
                """
                SELECT id, invoiceServiceYype, specification, unit, unitNumber, unitNumber2,
                       unitPrice, unitPrice2, originalUnitPrice, priceWithoutTax, taxRate, tax
                FROM fnainvoiceledgerdetail
                WHERE mainid = %s
                ORDER BY id
                LIMIT 500
                """,
                (invoice["id"],),
            )
            invoice["items"] = [self._normalize_row(row) for row in cursor.fetchall()]
        return invoices

    async def _compare(
        self,
        *,
        reconciliation_number: str,
        reconciliation: dict[str, Any],
        invoices: list[dict[str, Any]],
        amount_tolerance: Decimal,
        similarity_threshold: float,
        semantic_confidence_threshold: float,
        reference_source: str = "ecode 页面上下文",
    ) -> dict[str, Any]:
        header = reconciliation.get("header")
        if not header:
            return self._missing_evidence(f"未在采购对账单中找到“{reconciliation_number}”。")
        if not invoices:
            return self._missing_evidence("流程中的发票引用未关联到发票台账记录。")

        metadata = reconciliation["metadata"]
        fields = metadata["itemFields"]
        reconciliation_groups = self._aggregate_reconciliation_items(reconciliation["items"], fields)
        invoice_groups = self._aggregate_invoice_items(invoices)
        matches, unmatched_invoice, unmatched_reconciliation = await self._match_items_hybrid(
            invoice_groups,
            reconciliation_groups,
            similarity_threshold,
            amount_tolerance,
            semantic_confidence_threshold,
        )

        invoice_total = sum((self._decimal(item.get("taxincludedprice")) for item in invoices), Decimal("0"))
        expected_total = self._first_decimal(
            header,
            ["totalinvoiceamount", "settlementamount", "deliveryincludetaxamount"],
        )
        total_ok = expected_total is not None and abs(invoice_total - expected_total) <= amount_tolerance
        invoice_check_ok = all(str(item.get("checkstatus") or "") == "1" for item in invoices)
        comparison_keys = [
            "unitMatched",
            "quantityMatched",
            "amountMatched",
            "taxRateMatched",
        ]
        mismatch_matches = [
            item for item in matches if any(item.get(key) is False for key in comparison_keys)
        ]
        pending_matches = [
            item
            for item in matches
            if not any(item.get(key) is False for key in comparison_keys)
            and (
                any(item.get(key) is None for key in comparison_keys)
                or self._name_needs_review(item)
            )
        ]
        detail_failed = bool(unmatched_invoice or unmatched_reconciliation or mismatch_matches)
        detail_pending = bool(pending_matches) and not detail_failed

        detail_parts = [f"发票商品 {len(invoice_groups)} 项，对账物料 {len(reconciliation_groups)} 项"]
        if unmatched_invoice:
            detail_parts.append(
                "发票未匹配："
                + self._format_numbered_items(unmatched_invoice, lambda item: item["name"])
            )
        if unmatched_reconciliation:
            detail_parts.append(
                "对账单未匹配："
                + self._format_numbered_items(
                    unmatched_reconciliation,
                    lambda item: f"序号{self._format_sequences(item['sequences'])} {item['name']}",
                )
            )
        if mismatch_matches:
            detail_parts.append(
                "单位、数量、金额或税率不一致："
                + self._format_numbered_items(
                    mismatch_matches,
                    lambda item: (
                        f"序号{item['reconciliationSequence']} "
                        f"{item['reconciliationName']} ↔ {item['invoiceName']}"
                    ),
                )
            )
        if pending_matches:
            detail_parts.append(
                f"{len(pending_matches)} 项因名称匹配度不足100%或比较数据缺失，需人工核对"
            )

        checks = [
            {
                "name": "关联数据获取",
                "status": "pass",
                "detail": f"已关联对账单 {reconciliation_number} 和 {len(invoices)} 张发票。",
            },
            {
                "name": "发票查验状态",
                "status": "pass" if invoice_check_ok else "warning",
                "detail": "发票均已查验。" if invoice_check_ok else "存在发票未处于已查验状态，需人工确认真伪。",
            },
            {
                "name": "发票与对账单总额",
                "status": "pass" if total_ok else "fail",
                "detail": (
                    f"发票价税合计 {invoice_total:.2f}，对账单总发票金额 {expected_total:.2f}。"
                    if expected_total is not None
                    else f"发票价税合计 {invoice_total:.2f}，对账单未读取到可比较总额。"
                ),
            },
            {
                "name": "发票商品与对账物料",
                "status": "fail" if detail_failed else "warning" if detail_pending else "pass",
                "detail": "；".join(detail_parts) + "。",
            },
        ]
        failed = any(item["status"] == "fail" for item in checks)
        warned = any(item["status"] == "warning" for item in checks)
        concerns = [item["detail"] for item in checks if item["status"] in {"fail", "warning"}]
        comparison_rows = [
            {
                "reconciliationSequence": item["reconciliationSequence"],
                "invoiceName": item["invoiceName"],
                "reconciliationName": item["reconciliationName"],
                "invoiceSpecification": item["invoiceSpecification"],
                "reconciliationSpecification": item["reconciliationSpecification"],
                "invoiceUnit": item["invoiceUnit"],
                "reconciliationUnit": item["reconciliationUnit"],
                "invoiceQuantity": item["invoiceQuantity"],
                "reconciliationQuantity": item["reconciliationQuantity"],
                "invoiceAmount": item["invoiceAmount"],
                "reconciliationAmount": item["reconciliationAmount"],
                "invoiceTaxRates": item["invoiceTaxRates"],
                "reconciliationTaxRates": item["reconciliationTaxRates"],
                "nameStatus": "warning" if self._name_needs_review(item) else "pass",
                # 规格可能已并入对账物料描述，只展示，不单独判定。
                "specificationStatus": "unknown",
                "unitStatus": self._comparison_status(item["unitMatched"]),
                "quantityStatus": self._comparison_status(item["quantityMatched"]),
                "amountStatus": self._comparison_status(item["amountMatched"]),
                "taxRateStatus": self._comparison_status(item["taxRateMatched"]),
                "similarity": item["similarity"],
                "matchMethod": item["matchMethod"],
                "matchReason": item["matchReason"],
                "status": self._row_status(item, comparison_keys),
                "detail": self._comparison_detail(item),
            }
            for item in matches
        ]
        comparison_rows.extend(
            {
                "reconciliationSequence": None,
                "invoiceName": item["name"],
                "reconciliationName": None,
                "invoiceSpecification": self._format_text_values(item["specifications"]),
                "reconciliationSpecification": None,
                "invoiceUnit": self._format_text_values(item["units"]),
                "reconciliationUnit": None,
                "invoiceQuantity": self._format_decimal(item["quantity"]) if item["hasQuantity"] else None,
                "reconciliationQuantity": None,
                "invoiceAmount": str(item["untaxedAmount"]),
                "reconciliationAmount": None,
                "invoiceTaxRates": sorted(str(value) for value in item["taxRates"]),
                "reconciliationTaxRates": [],
                "nameStatus": "fail",
                "specificationStatus": "unknown",
                "unitStatus": "unknown",
                "quantityStatus": "unknown",
                "amountStatus": "unknown",
                "taxRateStatus": "unknown",
                "similarity": None,
                "matchMethod": "unmatched",
                "matchReason": "",
                "status": "fail",
                "detail": "发票商品未在对账单中找到匹配项",
            }
            for item in unmatched_invoice
        )
        comparison_rows.extend(
            {
                "reconciliationSequence": self._format_sequences(item["sequences"]),
                "invoiceName": None,
                "reconciliationName": item["name"],
                "invoiceSpecification": None,
                "reconciliationSpecification": self._format_text_values(item["specifications"]),
                "invoiceUnit": None,
                "reconciliationUnit": self._format_text_values(item["units"]),
                "invoiceQuantity": None,
                "reconciliationQuantity": (
                    self._format_decimal(item["quantity"]) if item["hasQuantity"] else None
                ),
                "invoiceAmount": None,
                "reconciliationAmount": str(item["untaxedAmount"]),
                "invoiceTaxRates": [],
                "reconciliationTaxRates": sorted(str(value) for value in item["taxRates"]),
                "nameStatus": "fail",
                "specificationStatus": "unknown",
                "unitStatus": "unknown",
                "quantityStatus": "unknown",
                "amountStatus": "unknown",
                "taxRateStatus": "unknown",
                "similarity": None,
                "matchMethod": "unmatched",
                "matchReason": "",
                "status": "fail",
                "detail": "对账物料未在发票中找到匹配项",
            }
            for item in unmatched_reconciliation
        )
        comparison_rows.sort(key=self._comparison_row_sort_key)
        return {
            "toolType": self.TOOL_TYPE,
            "status": "fail" if failed else "warning" if warned else "pass",
            "summary": "采购对账单与发票明细核验完成。",
            "checks": checks,
            "concerns": concerns,
            "facts": {
                "referenceSource": reference_source,
                "reconciliationNumber": reconciliation_number,
                "invoiceNumbers": [item.get("invoicenumber") for item in invoices],
                "invoiceTotal": str(invoice_total),
                "reconciliationTotal": str(expected_total) if expected_total is not None else None,
                "matchedItemCount": len(matches),
                "unmatchedInvoiceItemCount": len(unmatched_invoice),
                "unmatchedReconciliationItemCount": len(unmatched_reconciliation),
                "comparisonRows": comparison_rows[:500],
            },
        }

    def _comparison_detail(self, item: dict[str, Any]) -> str:
        labels = {
            "unitMatched": "单位",
            "quantityMatched": "数量",
            "amountMatched": "未税金额",
            "taxRateMatched": "税率",
        }
        problems = [f"{label}不一致" for key, label in labels.items() if item.get(key) is False]
        pending = [f"{label}缺少一侧数据" for key, label in labels.items() if item.get(key) is None]
        name_detail = ""
        if item.get("matchMethod") == "ai_semantic":
            name_detail = "AI语义确认同一商品"
            if item.get("matchReason"):
                name_detail += f"（{item['matchReason']}）"
        elif item.get("matchMethod") == "fallback_fuzzy":
            name_detail = "语义服务不可用，名称按高置信相似度匹配"
        else:
            name_detail = "采购物料描述与发票名称加规格一致"
        if self._name_needs_review(item):
            pending.insert(0, "名称匹配度不足100%")
        if problems:
            return f"{name_detail}；" + "、".join(problems)
        if pending:
            return f"{name_detail}；" + "；".join(pending) + "，需人工核对"
        return f"{name_detail}；单位、数量、未税金额和税率一致"

    def _name_needs_review(self, item: dict[str, Any]) -> bool:
        try:
            return float(item.get("similarity")) < 0.9999
        except (TypeError, ValueError):
            return True

    def _comparison_status(self, value: bool | None) -> str:
        if value is True:
            return "pass"
        if value is False:
            return "fail"
        return "unknown"

    def _row_status(self, item: dict[str, Any], keys: list[str]) -> str:
        values = [item.get(key) for key in keys]
        if any(value is False for value in values):
            return "fail"
        if any(value is None for value in values) or self._name_needs_review(item):
            return "warning"
        return "pass"

    def _format_numbered_items(
        self,
        items: list[dict[str, Any]],
        formatter: Any,
        *,
        limit: int = 20,
    ) -> str:
        circled = "①②③④⑤⑥⑦⑧⑨⑩"
        rendered: list[str] = []
        for index, item in enumerate(items[:limit], start=1):
            marker = circled[index - 1] if index <= len(circled) else f"({index})"
            rendered.append(f"{marker}{formatter(item)}")
        if len(items) > limit:
            rendered.append(f"另有{len(items) - limit}项")
        return "；".join(rendered)

    def _combine_invoice_name_and_specification(self, name: str, specification: str) -> str:
        if not specification:
            return name
        normalized_name = self._normalize_specification(name)
        normalized_specification = self._normalize_specification(specification)
        if normalized_specification and normalized_specification in normalized_name:
            return name
        return f"{name} {specification}".strip()

    def _extract_specification(self, name: str) -> str:
        text = self._text(name)
        slash_match = re.search(r"/([^/]+)$", text)
        if slash_match:
            return slash_match.group(1).strip()
        underscore_matches = re.findall(
            r"(?:^|_)(\d+(?:\.\d+)?(?:l|ml|kg|公斤)(?:\*\d+)?(?:_[^_]+)?)$",
            text,
            re.IGNORECASE,
        )
        return underscore_matches[-1].strip() if underscore_matches else ""

    def _normalize_specification(self, value: Any) -> str:
        return re.sub(r"[\s_*/×x-]+", "", self._text(value).lower()).replace("公斤", "kg")

    def _normalize_unit(self, value: Any) -> str:
        aliases = {
            "只": "个",
            "件": "个",
            "pcs": "个",
            "pc": "个",
            "吨": "t",
            "ton": "t",
            "千克": "kg",
            "公斤": "kg",
            "kgs": "kg",
            "克": "g",
            "毫克": "mg",
            "升": "l",
            "liter": "l",
            "litre": "l",
            "毫升": "ml",
            "立方米": "m3",
            "米": "m",
            "厘米": "cm",
            "毫米": "mm",
        }
        normalized = re.sub(r"\s+", "", self._text(value).lower())
        return aliases.get(normalized, normalized)

    def _normalize_unit_candidates(self, value: Any) -> set[str]:
        return {
            normalized
            for item in re.split(r"[、,，/;；|]+", self._text(value))
            if (normalized := self._normalize_unit(item))
        }

    def _compare_unit_sets(self, left: set[Any], right: set[Any]) -> bool | None:
        if not left or not right:
            return None

        left_groups = [self._normalize_unit_candidates(value) for value in left]
        right_groups = [self._normalize_unit_candidates(value) for value in right]
        left_groups = [group for group in left_groups if group]
        right_groups = [group for group in right_groups if group]
        if not left_groups or not right_groups:
            return None

        left_values = set().union(*left_groups)
        right_values = set().union(*right_groups)
        left_is_candidates = len(left_groups) == 1 and len(left_groups[0]) > 1
        right_is_candidates = len(right_groups) == 1 and len(right_groups[0]) > 1
        if left_is_candidates and not right_is_candidates:
            return right_values <= left_values
        if right_is_candidates and not left_is_candidates:
            return left_values <= right_values
        if left_values == right_values:
            return True
        left_conversion = self._unit_conversion(left_values)
        right_conversion = self._unit_conversion(right_values)
        return bool(
            left_conversion
            and right_conversion
            and left_conversion[0] == right_conversion[0]
        )

    def _unit_conversion(self, units: set[str]) -> tuple[str, Decimal] | None:
        if len(units) != 1:
            return None
        return self.UNIT_CONVERSIONS.get(next(iter(units)))

    def _compare_quantities_with_units(
        self,
        left: Decimal | None,
        left_units: set[Any],
        right: Decimal | None,
        right_units: set[Any],
    ) -> bool | None:
        if left is None or right is None:
            return None

        left_values = set().union(
            *(self._normalize_unit_candidates(value) for value in left_units)
        ) if left_units else set()
        right_values = set().union(
            *(self._normalize_unit_candidates(value) for value in right_units)
        ) if right_units else set()
        left_conversion = self._unit_conversion(left_values)
        right_conversion = self._unit_conversion(right_values)
        if left_conversion and right_conversion and left_conversion[0] == right_conversion[0]:
            return abs(left * left_conversion[1] - right * right_conversion[1]) <= Decimal("0.0001")
        return self._compare_optional_decimals(left, right)

    def _compare_text_sets(
        self,
        left: set[Any],
        right: set[Any],
        normalizer: Any,
    ) -> bool | None:
        if not left or not right:
            return None
        left_values = {normalizer(value) for value in left if normalizer(value)}
        right_values = {normalizer(value) for value in right if normalizer(value)}
        if not left_values or not right_values:
            return None
        return left_values == right_values

    def _compare_sets(self, left: set[Any], right: set[Any]) -> bool | None:
        if not left or not right:
            return None
        return left == right

    def _compare_optional_decimals(self, left: Decimal | None, right: Decimal | None) -> bool | None:
        if left is None or right is None:
            return None
        return abs(left - right) <= Decimal("0.0001")

    def _format_text_values(self, values: set[Any]) -> str | None:
        rendered = sorted({self._text(value) for value in values if self._text(value)})
        return "、".join(rendered) if rendered else None

    def _format_decimal(self, value: Decimal) -> str:
        return format(value.normalize(), "f")

    def _format_sequences(self, sequences: list[int]) -> str:
        return "、".join(str(value) for value in sorted(set(sequences)))

    def _comparison_row_sort_key(self, row: dict[str, Any]) -> tuple[int, int]:
        sequence = self._text(row.get("reconciliationSequence"))
        first = next((int(value) for value in re.findall(r"\d+", sequence)), 10**9)
        return (first, 1 if not sequence else 0)

    def _aggregate_reconciliation_items(
        self,
        items: list[dict[str, Any]],
        fields: dict[str, str | None],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for sequence, item in enumerate(items, start=1):
            name = self._text(item.get(fields["description"] or ""))
            explicit_specification = self._text(item.get(fields.get("specification") or ""))
            specification = explicit_specification or self._extract_specification(name)
            unit = self._text(item.get(fields.get("unit") or ""))
            normalized = self._normalize_item_name(name)
            if not normalized:
                continue
            group = grouped.setdefault(
                normalized,
                {
                    "name": name,
                    "normalized": normalized,
                    "untaxedAmount": Decimal("0"),
                    "taxedAmount": Decimal("0"),
                    "taxRates": set(),
                    "sequences": [],
                    "specifications": set(),
                    "units": set(),
                    "quantity": Decimal("0"),
                    "hasQuantity": False,
                },
            )
            group["sequences"].append(sequence)
            if specification:
                group["specifications"].add(specification)
            if unit:
                group["units"].add(unit)
            quantity = self._optional_decimal(item.get(fields.get("quantity") or ""))
            if quantity is not None:
                group["quantity"] += quantity
                group["hasQuantity"] = True
            group["untaxedAmount"] += self._decimal(item.get(fields.get("untaxedAmount") or ""))
            group["taxedAmount"] += self._decimal(item.get(fields.get("taxedAmount") or ""))
            tax_rate = self._optional_decimal(item.get(fields.get("taxRate") or ""))
            if tax_rate is not None:
                group["taxRates"].add(tax_rate)
        return list(grouped.values())

    def _aggregate_invoice_items(self, invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for invoice in invoices:
            for item in invoice.get("items") or []:
                name = self._text(item.get("invoiceserviceyype"))
                explicit_specification = self._text(item.get("specification"))
                specification = explicit_specification or self._extract_specification(name)
                combined_name = self._combine_invoice_name_and_specification(name, specification)
                normalized = self._normalize_item_name(combined_name)
                if not normalized:
                    continue
                group = grouped.setdefault(
                    normalized,
                    {
                        "name": name,
                        "combinedName": combined_name,
                        "normalized": normalized,
                        "untaxedAmount": Decimal("0"),
                        "taxRates": set(),
                        "specifications": set(),
                        "units": set(),
                        "quantity": Decimal("0"),
                        "hasQuantity": False,
                    },
                )
                if specification:
                    group["specifications"].add(specification)
                unit = self._text(item.get("unit"))
                if unit:
                    group["units"].add(unit)
                quantity = self._optional_decimal(item.get("unitnumber"))
                if quantity is None:
                    quantity = self._optional_decimal(item.get("unitnumber2"))
                if quantity is not None:
                    group["quantity"] += quantity
                    group["hasQuantity"] = True
                group["untaxedAmount"] += self._decimal(item.get("pricewithouttax"))
                tax_rate = self._optional_decimal(item.get("taxrate"))
                if tax_rate is not None:
                    group["taxRates"].add(tax_rate)
        return list(grouped.values())

    async def _match_items_hybrid(
        self,
        invoice_items: list[dict[str, Any]],
        reconciliation_items: list[dict[str, Any]],
        similarity_threshold: float,
        amount_tolerance: Decimal,
        semantic_confidence_threshold: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        exact_matches, unmatched_invoice, unmatched_reconciliation = self._match_items(
            invoice_items,
            reconciliation_items,
            1.0,
            amount_tolerance,
            match_method="exact_normalized",
        )
        if not unmatched_invoice or not unmatched_reconciliation:
            return exact_matches, unmatched_invoice, unmatched_reconciliation

        try:
            semantic_pairs = await self._semantic_match_items(
                unmatched_invoice,
                unmatched_reconciliation,
                confidence_threshold=semantic_confidence_threshold,
            )
        except Exception as exc:
            logger.warning(
                "泛微智审商品语义匹配失败，回退到高置信字符串匹配: "
                f"{LLMFactory.describe_invocation_error(exc)}"
            )
            fallback_matches, fallback_invoice, fallback_reconciliation = self._match_items(
                unmatched_invoice,
                unmatched_reconciliation,
                max(similarity_threshold, 0.92),
                amount_tolerance,
                match_method="fallback_fuzzy",
            )
            return (
                exact_matches + fallback_matches,
                fallback_invoice,
                fallback_reconciliation,
            )

        matched_invoice_indexes: set[int] = set()
        matched_reconciliation_indexes: set[int] = set()
        semantic_matches: list[dict[str, Any]] = []
        for pair in sorted(
            semantic_pairs,
            key=lambda item: float(item.get("confidence") or 0),
            reverse=True,
        ):
            invoice_index = pair["invoiceIndex"]
            reconciliation_index = pair["reconciliationIndex"]
            if (
                invoice_index in matched_invoice_indexes
                or reconciliation_index in matched_reconciliation_indexes
            ):
                continue
            matched_invoice_indexes.add(invoice_index)
            matched_reconciliation_indexes.add(reconciliation_index)
            semantic_matches.append(
                self._build_item_match(
                    unmatched_invoice[invoice_index],
                    unmatched_reconciliation[reconciliation_index],
                    score=float(pair["confidence"]),
                    amount_tolerance=amount_tolerance,
                    match_method="ai_semantic",
                    match_reason=self._text(pair.get("reason")),
                )
            )

        remaining_invoice = [
            item for index, item in enumerate(unmatched_invoice) if index not in matched_invoice_indexes
        ]
        remaining_reconciliation = [
            item
            for index, item in enumerate(unmatched_reconciliation)
            if index not in matched_reconciliation_indexes
        ]
        return exact_matches + semantic_matches, remaining_invoice, remaining_reconciliation

    async def _semantic_match_items(
        self,
        invoice_items: list[dict[str, Any]],
        reconciliation_items: list[dict[str, Any]],
        *,
        confidence_threshold: float,
    ) -> list[dict[str, Any]]:
        all_reconciliation_indexes = set(range(len(reconciliation_items)))
        batch_size = 30
        reconciliation_catalog = [
            self._semantic_reconciliation_payload(index, item)
            for index, item in enumerate(reconciliation_items)
        ]
        batches: list[tuple[dict[str, Any], set[tuple[int, int]]]] = []
        for start in range(0, len(invoice_items), batch_size):
            invoice_indexes = list(range(start, min(start + batch_size, len(invoice_items))))
            allowed_pairs = {
                (invoice_index, reconciliation_index)
                for invoice_index in invoice_indexes
                for reconciliation_index in all_reconciliation_indexes
            }
            request_payload = {
                "invoiceItems": [
                    self._semantic_invoice_payload(invoice_index, invoice_items[invoice_index])
                    for invoice_index in invoice_indexes
                ],
                "reconciliationCatalog": reconciliation_catalog,
            }
            batches.append((request_payload, allowed_pairs))

        semaphore = asyncio.Semaphore(3)

        async def invoke_batch(request_payload: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self._invoke_semantic_match_model(request_payload)

        responses = await asyncio.gather(
            *(invoke_batch(request_payload) for request_payload, _ in batches),
            return_exceptions=True,
        )
        proposed_pairs: list[dict[str, Any]] = []
        failed_batches: list[BaseException] = []
        for (_, allowed_pairs), response in zip(batches, responses, strict=True):
            if isinstance(response, BaseException):
                failed_batches.append(response)
                logger.warning(
                    "泛微智审商品语义匹配批次失败，跳过该批次: "
                    f"{LLMFactory.describe_invocation_error(response)}"
                )
                continue
            for raw in response.get("matches") or []:
                if not isinstance(raw, dict):
                    continue
                invoice_index = self._semantic_id(raw.get("invoiceId"), "I")
                reconciliation_index = self._semantic_id(raw.get("reconciliationId"), "R")
                confidence = self._bounded_float(raw.get("confidence"), 0)
                if (
                    invoice_index is None
                    or reconciliation_index is None
                    or (invoice_index, reconciliation_index) not in allowed_pairs
                    or confidence < confidence_threshold
                ):
                    continue
                proposed_pairs.append(
                    {
                        "invoiceIndex": invoice_index,
                        "reconciliationIndex": reconciliation_index,
                        "confidence": confidence,
                        "reason": self._text(raw.get("reason"))[:300],
                    }
                )
        if failed_batches:
            raise RuntimeError(
                f"{len(failed_batches)} 个商品语义匹配批次调用失败"
            ) from failed_batches[-1]

        accepted: list[dict[str, Any]] = []
        used_invoice: set[int] = set()
        used_reconciliation: set[int] = set()
        for pair in sorted(
            proposed_pairs,
            key=lambda item: float(item["confidence"]),
            reverse=True,
        ):
            invoice_index = pair["invoiceIndex"]
            reconciliation_index = pair["reconciliationIndex"]
            if invoice_index in used_invoice or reconciliation_index in used_reconciliation:
                continue
            used_invoice.add(invoice_index)
            used_reconciliation.add(reconciliation_index)
            accepted.append(pair)
        return accepted

    def _semantic_invoice_payload(self, index: int, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"I{index}",
            "name": item["name"],
            "specification": self._format_text_values(item["specifications"]),
            "combinedDescription": item.get("combinedName") or item["name"],
            "quantity": self._format_decimal(item["quantity"]) if item["hasQuantity"] else None,
            "untaxedAmount": str(item["untaxedAmount"]),
            "taxRates": sorted(str(value) for value in item["taxRates"]),
        }

    def _semantic_reconciliation_payload(self, index: int, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"R{index}",
            "sequence": self._format_sequences(item["sequences"]),
            "purchaseMaterialDescription": item["name"],
            "quantity": self._format_decimal(item["quantity"]) if item["hasQuantity"] else None,
            "untaxedAmount": str(item["untaxedAmount"]),
            "taxRates": sorted(str(value) for value in item["taxRates"]),
        }

    async def _invoke_semantic_match_model(
        self,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        messages = [
            SystemMessage(
                content=(
                    "你是企业采购发票商品语义匹配器。任务是判断发票商品与采购对账物料是否指向同一种实际商品，"
                    "不能只按字符相似度判断。需要综合商品类别、用途、材质、行业同义词、型号、颜色、容量、包装和计量信息；"
                    "发票名称中的税收分类前缀可能比采购名称宽泛，发票规格也可能是采购物料描述的一部分。"
                    "数量、未税金额和税率只能帮助候选消歧，不能把明显不同的商品强行匹配。"
                    "请在 reconciliationCatalog 完整目录中为 invoiceItems 寻找同一商品。"
                    "每个发票商品最多匹配一个对账物料，每个对账物料最多使用一次；不确定时不要输出该项。"
                    "只返回JSON：{\"matches\":[{\"invoiceId\":\"I0\",\"reconciliationId\":\"R1\","
                    "\"confidence\":0.92,\"reason\":\"简短业务理由\"}]}。"
                )
            ),
            HumanMessage(
                content=json.dumps(
                    request_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ),
        ]
        model_name = (settings.WEAVER_AI_MODEL_NAME or "").strip()
        response = await LLMFactory.safe_invoke(
            messages,
            capability=settings.WEAVER_AI_MODEL_CAPABILITY or "complex-reasoning",
            preferred_model_names=[model_name] if model_name else None,
            json_mode=True,
            temperature=0,
            enable_reasoning=settings.WEAVER_AI_ENABLE_REASONING,
            max_retries=4,
            invocation_timeout_seconds=45,
            langfuse_run_name="weaver_invoice_semantic_match",
            langfuse_metadata={"domain": "weaver_ai_review"},
            langfuse_tags=["weaver", "invoice", "semantic-match"],
        )
        return self._parse_json_object(getattr(response, "content", response))

    def _parse_json_object(self, value: Any) -> dict[str, Any]:
        text = self._text(value)
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("商品语义匹配模型未返回JSON对象")
        return parsed

    def _semantic_id(self, value: Any, prefix: str) -> int | None:
        match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", self._text(value))
        return int(match.group(1)) if match else None

    def _match_items(
        self,
        invoice_items: list[dict[str, Any]],
        reconciliation_items: list[dict[str, Any]],
        similarity_threshold: float,
        amount_tolerance: Decimal,
        *,
        match_method: str = "deterministic_fuzzy",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        available = set(range(len(reconciliation_items)))
        matches: list[dict[str, Any]] = []
        unmatched_invoice: list[dict[str, Any]] = []
        for invoice in invoice_items:
            candidates = sorted(
                (
                    (self._item_similarity(invoice["normalized"], reconciliation_items[index]["normalized"]), index)
                    for index in available
                ),
                reverse=True,
            )
            if not candidates or candidates[0][0] < similarity_threshold:
                unmatched_invoice.append(invoice)
                continue
            score, index = candidates[0]
            reconciliation = reconciliation_items[index]
            available.remove(index)
            matches.append(
                self._build_item_match(
                    invoice,
                    reconciliation,
                    score=score,
                    amount_tolerance=amount_tolerance,
                    match_method=match_method,
                )
            )
        return matches, unmatched_invoice, [reconciliation_items[index] for index in sorted(available)]

    def _build_item_match(
        self,
        invoice: dict[str, Any],
        reconciliation: dict[str, Any],
        *,
        score: float,
        amount_tolerance: Decimal,
        match_method: str,
        match_reason: str = "",
    ) -> dict[str, Any]:
        return {
            "invoiceName": invoice["name"],
            "reconciliationName": reconciliation["name"],
            "reconciliationSequence": self._format_sequences(reconciliation["sequences"]),
            "invoiceSpecification": self._format_text_values(invoice["specifications"]),
            "reconciliationSpecification": self._format_text_values(reconciliation["specifications"]),
            "invoiceUnit": self._format_text_values(invoice["units"]),
            "reconciliationUnit": self._format_text_values(reconciliation["units"]),
            "invoiceQuantity": self._format_decimal(invoice["quantity"]) if invoice["hasQuantity"] else None,
            "reconciliationQuantity": (
                self._format_decimal(reconciliation["quantity"]) if reconciliation["hasQuantity"] else None
            ),
            "invoiceAmount": str(invoice["untaxedAmount"]),
            "reconciliationAmount": str(reconciliation["untaxedAmount"]),
            "invoiceTaxRates": sorted(str(value) for value in invoice["taxRates"]),
            "reconciliationTaxRates": sorted(str(value) for value in reconciliation["taxRates"]),
            "similarity": round(score, 4),
            "matchMethod": match_method,
            "matchReason": match_reason,
            "nameMatched": True,
            "specificationMatched": self._compare_text_sets(
                invoice["specifications"],
                reconciliation["specifications"],
                self._normalize_specification,
            ),
            "unitMatched": self._compare_unit_sets(
                invoice["units"],
                reconciliation["units"],
            ),
            "quantityMatched": self._compare_quantities_with_units(
                invoice["quantity"] if invoice["hasQuantity"] else None,
                invoice["units"],
                reconciliation["quantity"] if reconciliation["hasQuantity"] else None,
                reconciliation["units"],
            ),
            "amountMatched": (
                abs(invoice["untaxedAmount"] - reconciliation["untaxedAmount"]) <= amount_tolerance
            ),
            "taxRateMatched": self._compare_sets(invoice["taxRates"], reconciliation["taxRates"]),
        }

    def _item_similarity(self, left: str, right: str) -> float:
        if left == right:
            return 1.0
        score = SequenceMatcher(None, left, right).ratio()
        if left in right or right in left:
            score = max(score, 0.9)
        left_specs = set(re.findall(r"\d+(?:\.\d+)?(?:l|kg|公斤|ml)(?:\*\d+)?", left, re.IGNORECASE))
        right_specs = set(re.findall(r"\d+(?:\.\d+)?(?:l|kg|公斤|ml)(?:\*\d+)?", right, re.IGNORECASE))
        if left_specs and right_specs and left_specs.isdisjoint(right_specs):
            score = min(score, 0.6)
        product_words = {"大豆油", "玉米油", "菜籽油", "纸箱"}
        left_products = {word for word in product_words if word in left}
        right_products = {word for word in product_words if word in right}
        if left_products and right_products and left_products.isdisjoint(right_products):
            score = min(score, 0.5)
        return score

    def _enabled_tools(self, rules: list[WeaverReviewRuleRead]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for rule in rules:
            config = rule.tool_config or {}
            tools = config.get("tools") if isinstance(config.get("tools"), list) else []
            for tool in tools:
                if not isinstance(tool, dict) or tool.get("enabled") is False:
                    continue
                key = (self._text(tool.get("type")), self._text(tool.get("customId")))
                if key in seen:
                    continue
                seen.add(key)
                result.append(tool)
        return result

    def _find_context_value(self, payload: WeaverReviewRequest, labels: list[Any], *, prefer_text: bool) -> str:
        values = self._find_context_values(payload, labels)
        if not values:
            return ""
        if prefer_text:
            for value in values:
                if not value.isdigit():
                    return value
        return values[0]

    def _find_context_values(self, payload: WeaverReviewRequest, labels: list[Any]) -> list[str]:
        expected = {self._normalize_label(label) for label in labels if self._text(label)}
        result: list[str] = []
        for field in payload.context.fields.values():
            normalized_label = self._normalize_label(field.label)
            if not normalized_label or not any(label in normalized_label or normalized_label in label for label in expected):
                continue
            for raw in (field.value, field.display_value):
                for value in self._flatten_values(raw):
                    if value and value not in result:
                        result.append(value)
        return result

    def _flatten_values(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                result.extend(self._flatten_values(item))
            return result
        if isinstance(value, dict):
            result: list[str] = []
            for key in ("id", "value", "name", "displayValue"):
                if key in value:
                    result.extend(self._flatten_values(value[key]))
            return result
        text = self._text(value)
        if not text:
            return []
        return [part.strip() for part in re.split(r"[,，;；\s]+", text) if part.strip()]

    def _field_by_label(self, fields: list[dict[str, Any]], labels: list[str], *, detail: bool) -> dict[str, Any]:
        for label in labels:
            for field in fields:
                has_detail = bool(self._text(field.get("detailtable")))
                if has_detail != detail:
                    continue
                if self._normalize_label(field.get("labelname")) == self._normalize_label(label):
                    return field
        raise ValueError(f"建模表单缺少字段：{'/'.join(labels)}")

    def _optional_field(
        self,
        fields: list[dict[str, Any]],
        detail_table: str,
        labels: list[str],
        *,
        field_names: list[str] | None = None,
    ) -> str | None:
        expected_field_names = {self._text(value).lower() for value in field_names or []}
        for label in labels:
            for field in fields:
                if self._text(field.get("detailtable")).lower() != detail_table.lower():
                    continue
                if self._normalize_label(field.get("labelname")) == self._normalize_label(label):
                    return self._identifier(field.get("fieldname"))
        for field in fields:
            if self._text(field.get("detailtable")).lower() != detail_table.lower():
                continue
            if self._text(field.get("fieldname")).lower() in expected_field_names:
                return self._identifier(field.get("fieldname"))
        return None

    def _missing_evidence(self, detail: str) -> dict[str, Any]:
        return {
            "toolType": self.TOOL_TYPE,
            "status": "warning",
            "summary": "采购对账单与发票明细未完成核验。",
            "checks": [{"name": "关联数据核验", "status": "warning", "detail": detail}],
            "concerns": [detail],
        }

    def _identifier(self, value: Any) -> str:
        text = self._text(value)
        if not self.IDENTIFIER_PATTERN.fullmatch(text):
            raise ValueError(f"非法数据库标识符：{text}")
        return text

    def _positive_int(self, value: Any, label: str) -> int:
        number = int(value)
        if number <= 0:
            raise ValueError(f"{label}必须为正整数")
        return number

    def _bounded_float(self, value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return min(max(number, 0.5), 1.0)

    def _first_decimal(self, row: dict[str, Any], keys: list[str]) -> Decimal | None:
        for key in keys:
            value = self._optional_decimal(row.get(key))
            if value is not None:
                return value
        return None

    def _decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        parsed = self._optional_decimal(value)
        return parsed if parsed is not None else default

    def _optional_decimal(self, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _normalize_row(self, row: dict[str, Any] | None) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in (row or {}).items()}

    def _normalize_item_name(self, value: Any) -> str:
        text = self._text(value).lower()
        text = re.sub(r"\*[^*]+\*", "", text)
        text = text.replace("千克", "kg").replace("公斤", "kg").replace("升", "l")
        return re.sub(r"[\s_（）()【】\[\]，,。.;；:：/\\\-]+", "", text)

    def _normalize_label(self, value: Any) -> str:
        return re.sub(r"[\s:：()（）]+", "", self._text(value)).lower()

    def _text(self, value: Any) -> str:
        return "" if value is None else str(value).strip()


weaver_review_evidence_service = WeaverReviewEvidenceService()
