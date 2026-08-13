import asyncio
from decimal import Decimal

from app.services.agent.weaver_ai_assistant.review_evidence_service import WeaverReviewEvidenceService


def test_item_name_normalization_ignores_invoice_category_prefix() -> None:
    service = WeaverReviewEvidenceService()

    invoice_name = service._normalize_item_name("*纸制品*纸箱_天下五谷一级大豆油/10L*2")
    reconciliation_name = service._normalize_item_name("纸箱_天下五谷一级大豆油/10L*2")

    assert invoice_name == reconciliation_name


def test_item_matching_aggregates_rows_before_comparison() -> None:
    service = WeaverReviewEvidenceService()
    reconciliation_items = service._aggregate_reconciliation_items(
        [
            {"materialdesc": "纸箱_天下五谷一级大豆油/10L*2", "totalnontaxamount": "10.01", "taxrate": "13"},
            {"materialdesc": "纸箱_天下五谷一级大豆油/10L*2", "totalnontaxamount": "20.02", "taxrate": "13"},
        ],
        {
            "description": "materialdesc",
            "code": None,
            "quantity": None,
            "untaxedAmount": "totalnontaxamount",
            "taxedAmount": None,
            "taxRate": "taxrate",
        },
    )
    invoice_items = service._aggregate_invoice_items(
        [
            {
                "items": [
                    {
                        "invoiceserviceyype": "*纸制品*纸箱_天下五谷一级大豆油/10L*2",
                        "pricewithouttax": "30.03",
                        "taxrate": "13",
                    }
                ]
            }
        ]
    )

    matches, unmatched_invoice, unmatched_reconciliation = service._match_items(
        invoice_items,
        reconciliation_items,
        similarity_threshold=0.78,
        amount_tolerance=Decimal("0.10"),
    )

    assert len(matches) == 1
    assert matches[0]["amountMatched"] is True
    assert matches[0]["taxRateMatched"] is True
    assert matches[0]["invoiceAmount"] == "30.03"
    assert matches[0]["reconciliationAmount"] == "30.03"
    assert matches[0]["invoiceTaxRates"] == ["13"]
    assert unmatched_invoice == []
    assert unmatched_reconciliation == []


def test_item_matching_rejects_conflicting_specification() -> None:
    service = WeaverReviewEvidenceService()

    score = service._item_similarity(
        service._normalize_item_name("纸箱_天下五谷一级大豆油/10L*2"),
        service._normalize_item_name("纸箱_天下五谷一级大豆油/5L*4"),
    )

    assert score < 0.78


def test_invoice_name_and_specification_match_combined_reconciliation_material() -> None:
    service = WeaverReviewEvidenceService()
    reconciliation_items = service._aggregate_reconciliation_items(
        [
            {
                "materialdesc": "纸箱_非转基因一级大豆油（福建军供）/4.5公斤*4",
                "voucherquantity": "8",
                "totalnontaxamount": "100",
                "taxrate": "9",
            }
        ],
        {
            "description": "materialdesc",
            "code": None,
            "specification": None,
            "unit": None,
            "quantity": "voucherquantity",
            "untaxedAmount": "totalnontaxamount",
            "taxedAmount": None,
            "taxRate": "taxrate",
        },
    )
    invoice_items = service._aggregate_invoice_items(
        [
            {
                "items": [
                    {
                        "invoiceserviceyype": "纸箱_非转基因一级大豆油（福建军供）",
                        "specification": "4.5公斤*4",
                        "unit": "个",
                        "unitnumber": None,
                        "unitnumber2": "8",
                        "pricewithouttax": "100",
                        "taxrate": "9",
                    }
                ]
            }
        ]
    )

    matches, unmatched_invoice, unmatched_reconciliation = service._match_items(
        invoice_items,
        reconciliation_items,
        similarity_threshold=0.78,
        amount_tolerance=Decimal("0.10"),
    )

    assert len(matches) == 1
    assert matches[0]["invoiceName"] == "纸箱_非转基因一级大豆油（福建军供）"
    assert matches[0]["invoiceSpecification"] == "4.5公斤*4"
    assert matches[0]["reconciliationSpecification"] == "4.5公斤*4"
    assert matches[0]["specificationMatched"] is True
    assert matches[0]["quantityMatched"] is True
    assert unmatched_invoice == []
    assert unmatched_reconciliation == []


def test_hybrid_matching_uses_ai_for_semantically_equivalent_complex_names() -> None:
    service = WeaverReviewEvidenceService()
    invoice_items = service._aggregate_invoice_items(
        [
            {
                "items": [
                    {
                        "invoiceserviceyype": "工业涂料 环氧树脂漆",
                        "specification": "灰 20千克",
                        "unitnumber": "3",
                        "pricewithouttax": "1200",
                        "taxrate": "13",
                    }
                ]
            }
        ]
    )
    reconciliation_items = service._aggregate_reconciliation_items(
        [
            {
                "materialdesc": "加厚耐磨环氧底漆灰色20KG",
                "voucherquantity": "3",
                "totalnontaxamount": "1200",
                "taxrate": "13",
            }
        ],
        {
            "description": "materialdesc",
            "code": None,
            "specification": None,
            "unit": None,
            "quantity": "voucherquantity",
            "untaxedAmount": "totalnontaxamount",
            "taxedAmount": None,
            "taxRate": "taxrate",
        },
    )

    async def fake_semantic_model(_: dict) -> dict:
        return {
            "matches": [
                {
                    "invoiceId": "I0",
                    "reconciliationId": "R0",
                    "confidence": 0.95,
                    "reason": "均为灰色20KG环氧树脂类工业涂料",
                }
            ]
        }

    service._invoke_semantic_match_model = fake_semantic_model  # type: ignore[method-assign]
    matches, unmatched_invoice, unmatched_reconciliation = asyncio.run(
        service._match_items_hybrid(
            invoice_items,
            reconciliation_items,
            similarity_threshold=0.78,
            amount_tolerance=Decimal("0.10"),
            semantic_confidence_threshold=0.72,
        )
    )

    assert len(matches) == 1
    assert matches[0]["matchMethod"] == "ai_semantic"
    assert matches[0]["similarity"] == 0.95
    assert matches[0]["quantityMatched"] is True
    assert unmatched_invoice == []
    assert unmatched_reconciliation == []


def test_hybrid_matching_rejects_unlisted_or_low_confidence_ai_pairs() -> None:
    service = WeaverReviewEvidenceService()
    invoice_items = service._aggregate_invoice_items(
        [{"items": [{"invoiceserviceyype": "工业涂料", "pricewithouttax": "10"}]}]
    )
    reconciliation_items = service._aggregate_reconciliation_items(
        [{"materialdesc": "办公用纸", "totalnontaxamount": "10"}],
        {
            "description": "materialdesc",
            "code": None,
            "specification": None,
            "unit": None,
            "quantity": None,
            "untaxedAmount": "totalnontaxamount",
            "taxedAmount": None,
            "taxRate": None,
        },
    )

    async def fake_semantic_model(_: dict) -> dict:
        return {
            "matches": [
                {
                    "invoiceId": "I0",
                    "reconciliationId": "R0",
                    "confidence": 0.4,
                    "reason": "证据不足",
                },
                {
                    "invoiceId": "I0",
                    "reconciliationId": "R99",
                    "confidence": 0.99,
                    "reason": "非法候选",
                },
            ]
        }

    service._invoke_semantic_match_model = fake_semantic_model  # type: ignore[method-assign]
    matches, unmatched_invoice, unmatched_reconciliation = asyncio.run(
        service._match_items_hybrid(
            invoice_items,
            reconciliation_items,
            similarity_threshold=0.78,
            amount_tolerance=Decimal("0.10"),
            semantic_confidence_threshold=0.72,
        )
    )

    assert matches == []
    assert len(unmatched_invoice) == 1
    assert len(unmatched_reconciliation) == 1


def test_prefer_text_value_uses_business_number_before_browser_id() -> None:
    service = WeaverReviewEvidenceService()

    assert service._prefer_text_value(["353", "PR202606220088"]) == "PR202606220088"


def test_label_matching_accepts_main_table_suffix() -> None:
    service = WeaverReviewEvidenceService()

    assert service._label_matches("对账单号主表", {service._normalize_label("对账单号")}) is True


def test_optional_unit_field_falls_back_to_dw_field_name() -> None:
    service = WeaverReviewEvidenceService()
    fields = [
        {"fieldname": "dw", "detailtable": "formtable_main_1_dt1", "labelname": "计量"},
    ]

    field_name = service._optional_field(
        fields,
        "formtable_main_1_dt1",
        ["计量单位", "单位"],
        field_names=["dw"],
    )

    assert field_name == "dw"


def test_non_exact_name_is_pending_when_other_values_match() -> None:
    service = WeaverReviewEvidenceService()
    item = {
        "similarity": 0.95,
        "unitMatched": True,
        "quantityMatched": True,
        "amountMatched": True,
        "taxRateMatched": True,
    }

    assert service._name_needs_review(item) is True
    assert (
        service._row_status(
            item,
            ["unitMatched", "quantityMatched", "amountMatched", "taxRateMatched"],
        )
        == "warning"
    )


def test_unit_mismatch_is_error_even_when_name_needs_review() -> None:
    service = WeaverReviewEvidenceService()
    item = {
        "similarity": 0.95,
        "unitMatched": False,
        "quantityMatched": True,
        "amountMatched": True,
        "taxRateMatched": True,
    }

    assert (
        service._row_status(
            item,
            ["unitMatched", "quantityMatched", "amountMatched", "taxRateMatched"],
        )
        == "fail"
    )


def test_invoice_unit_matches_reconciliation_candidate_units() -> None:
    service = WeaverReviewEvidenceService()

    assert service._compare_unit_sets({"套"}, {"套、双、副"}) is True
    assert service._compare_unit_sets({"箱"}, {"套、双、副"}) is False


def test_parenthesized_unit_aliases_are_equivalent() -> None:
    service = WeaverReviewEvidenceService()

    assert service._compare_unit_sets({"千克"}, {"千克(公斤)"}) is True
    assert service._compare_unit_sets({"kg"}, {"千克（公斤）"}) is True


def test_kilometers_and_meters_are_converted_with_quantities() -> None:
    service = WeaverReviewEvidenceService()

    assert service._compare_unit_sets({"KM"}, {"米"}) is True
    assert service._compare_quantities_with_units(
        Decimal("0.123"),
        {"KM"},
        Decimal("123"),
        {"米"},
    ) is True


def test_ai_unit_review_marks_uncertain_result_as_pending() -> None:
    service = WeaverReviewEvidenceService()
    matches = [
        {
            "invoiceName": "测试商品",
            "reconciliationName": "测试商品",
            "invoiceUnit": "包",
            "reconciliationUnit": "箱",
            "invoiceQuantity": "10",
            "reconciliationQuantity": "1",
            "unitMatched": False,
            "quantityMatched": False,
        }
    ]

    async def fake_review(_: dict[str, object]) -> dict[str, object]:
        return {
            "results": [
                {
                    "id": "U0",
                    "verdict": "uncertain",
                    "confidence": 0.85,
                    "reason": "未提供每箱包含多少包",
                }
            ]
        }

    service._invoke_unit_equivalence_model = fake_review  # type: ignore[method-assign]
    asyncio.run(service._review_ambiguous_units(matches))

    assert matches[0]["unitMatched"] is None
    assert matches[0]["quantityMatched"] is None


def test_ai_unit_review_accepts_only_verified_quantity_conversion() -> None:
    service = WeaverReviewEvidenceService()
    matches = [
        {
            "invoiceName": "电缆",
            "reconciliationName": "电缆",
            "invoiceUnit": "卷",
            "reconciliationUnit": "米",
            "invoiceQuantity": "2",
            "reconciliationQuantity": "200",
            "unitMatched": False,
            "quantityMatched": False,
        }
    ]

    async def fake_review(_: dict[str, object]) -> dict[str, object]:
        return {
            "results": [
                {
                    "id": "U0",
                    "verdict": "equivalent",
                    "invoiceToReconciliationFactor": 100,
                    "confidence": 0.97,
                    "reason": "规格表明每卷100米",
                }
            ]
        }

    service._invoke_unit_equivalence_model = fake_review  # type: ignore[method-assign]
    asyncio.run(service._review_ambiguous_units(matches))

    assert matches[0]["unitMatched"] is True
    assert matches[0]["quantityMatched"] is True


def test_multiple_actual_units_are_not_treated_as_candidates() -> None:
    service = WeaverReviewEvidenceService()

    assert service._compare_unit_sets({"套", "双"}, {"套"}) is False


def test_convertible_mass_units_and_quantities_are_equivalent() -> None:
    service = WeaverReviewEvidenceService()

    assert service._compare_unit_sets({"吨"}, {"千克"}) is True
    assert (
        service._compare_quantities_with_units(
            Decimal("91.12"),
            {"吨"},
            Decimal("91120"),
            {"千克"},
        )
        is True
    )


def test_convertible_units_still_fail_when_base_quantities_differ() -> None:
    service = WeaverReviewEvidenceService()

    assert (
        service._compare_quantities_with_units(
            Decimal("91.12"),
            {"吨"},
            Decimal("91121"),
            {"千克"},
        )
        is False
    )
