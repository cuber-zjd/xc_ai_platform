import asyncio
from unittest.mock import AsyncMock

import pytest

from app.schemas.agent.weaver_ai_assistant import WeaverReviewNodeStatus
from app.services.agent.weaver_ai_assistant.review_service import (
    WeaverAiReviewService,
    WeaverReviewNodeDisabledError,
)


def _status(*, enabled: bool, automatic: bool) -> WeaverReviewNodeStatus:
    return WeaverReviewNodeStatus(
        env="test",
        workflowId="365",
        nodeId="2673",
        configured=True,
        enabled=enabled,
        showEntry=enabled,
        automaticReviewEnabled=automatic,
    )


def test_unconfigured_or_disabled_node_cannot_run_manual_review() -> None:
    service = WeaverAiReviewService()
    service.get_node_status = AsyncMock(return_value=_status(enabled=False, automatic=False))  # type: ignore[method-assign]

    with pytest.raises(WeaverReviewNodeDisabledError, match="未在智审配置页启用"):
        asyncio.run(service.ensure_node_review_enabled(None, "test", "365", "2673", "manual"))  # type: ignore[arg-type]


def test_enabled_node_can_run_manual_review_without_automatic_switch() -> None:
    service = WeaverAiReviewService()
    expected = _status(enabled=True, automatic=False)
    service.get_node_status = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    actual = asyncio.run(service.ensure_node_review_enabled(None, "test", "365", "2673", "manual"))  # type: ignore[arg-type]

    assert actual == expected


def test_action_requires_automatic_review_switch() -> None:
    service = WeaverAiReviewService()
    service.get_node_status = AsyncMock(return_value=_status(enabled=True, automatic=False))  # type: ignore[method-assign]

    with pytest.raises(WeaverReviewNodeDisabledError, match="未开启自动预审"):
        asyncio.run(service.ensure_node_review_enabled(None, "test", "365", "2673", "action"))  # type: ignore[arg-type]


def test_action_runs_when_node_and_automatic_review_are_enabled() -> None:
    service = WeaverAiReviewService()
    expected = _status(enabled=True, automatic=True)
    service.get_node_status = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    actual = asyncio.run(service.ensure_node_review_enabled(None, "test", "365", "2673", "action"))  # type: ignore[arg-type]

    assert actual == expected
