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


def test_prefer_text_value_uses_business_number_before_browser_id() -> None:
    service = WeaverReviewEvidenceService()

    assert service._prefer_text_value(["353", "PR202606220088"]) == "PR202606220088"


def test_label_matching_accepts_main_table_suffix() -> None:
    service = WeaverReviewEvidenceService()

    assert service._label_matches("对账单号主表", {service._normalize_label("对账单号")}) is True
