import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.models.agent.weaver_ai_assistant import (
    WeaverAiReviewRecord,
    WeaverAiReviewTestRecord,
)
from app.schemas.agent.weaver_ai_assistant import (
    WeaverFieldConfigResponse,
    WeaverFormContext,
    WeaverReviewResult,
    WeaverReviewTestRequest,
)
from app.services.agent.weaver_ai_assistant import review_service as review_service_module
from app.services.agent.weaver_ai_assistant.review_service import WeaverAiReviewService


class _FakeSession:
    def __init__(self) -> None:
        self.added = None
        self.commit = AsyncMock()

    def add(self, row: object) -> None:
        self.added = row

    async def refresh(self, row: object) -> None:
        row.id = 17  # type: ignore[attr-defined]


def test_test_review_ignores_node_switch_and_uses_separate_record(monkeypatch) -> None:
    service = WeaverAiReviewService()
    db = _FakeSession()
    metadata = WeaverFieldConfigResponse(
        workflowId="433",
        env="prod",
        workflowName="电采供应商付款单",
        mainTable="formtable_main_1",
    )
    context = WeaverFormContext(
        env="prod",
        baseInfo={"workflowid": "433", "requestid": "1994995"},
    )
    expected_result = WeaverReviewResult(
        summary="测试智审完成",
        riskLevel="low",
        decisionSuggestion="approve",
        suggestedOpinion="建议同意",
        confidence=0.96,
        canAutoApprove=True,
    )

    monkeypatch.setattr(
        review_service_module.weaver_ai_assistant_service,
        "get_field_config",
        AsyncMock(return_value=metadata),
    )
    monkeypatch.setattr(
        review_service_module.weaver_review_evidence_service,
        "collect",
        AsyncMock(return_value=[]),
    )
    service._load_test_request_context = MagicMock(  # type: ignore[method-assign]
        return_value=(context, {"testMode": True}, "9001", "财务审批")
    )
    service.load_all_enabled_rules_for_test = AsyncMock(return_value=[])  # type: ignore[method-assign]
    service.invoke_review_model = AsyncMock(return_value=expected_result)  # type: ignore[method-assign]
    service.ensure_node_review_enabled = AsyncMock(  # type: ignore[method-assign]
        side_effect=AssertionError("测试审批不应校验当前节点开关")
    )

    response = asyncio.run(
        service.test_review(
            db,  # type: ignore[arg-type]
            WeaverReviewTestRequest(env="prod", workflowId="433", requestId="1994995"),
        )
    )

    assert isinstance(db.added, WeaverAiReviewTestRecord)
    assert not isinstance(db.added, WeaverAiReviewRecord)
    assert db.added.source_node_id == "9001"
    assert db.added.request_id == "1994995"
    assert response.record.trigger_type == "test"
    assert response.source_node_name == "财务审批"
    service.ensure_node_review_enabled.assert_not_awaited()


def test_test_review_rejects_unsafe_table_identifier() -> None:
    service = WeaverAiReviewService()

    try:
        service._safe_identifier("formtable_main_1; DROP TABLE x", "流程主表")
    except ValueError as exc:
        assert str(exc) == "流程主表不合法"
    else:
        raise AssertionError("非法表名必须被拒绝")
