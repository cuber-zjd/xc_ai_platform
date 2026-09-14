"""飞书简报本期调整的保存与重新读取回归验证。"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.agent.insight import InsightFeishuBriefOccurrence, InsightFeishuBriefPlan
from app.schemas.agent.insight.feishu_brief import InsightFeishuBriefOccurrenceOverride
from app.services.agent.insight.feishu_brief_service import InsightFeishuBriefService


@pytest.mark.asyncio
async def test_saved_occurrence_is_returned_after_reopening_plan(monkeypatch):
    service = InsightFeishuBriefService()
    plan = InsightFeishuBriefPlan(id=1, plan_uid="回归计划", plan_name="周报", owner_user_id=1)
    occurrence = InsightFeishuBriefOccurrence(
        id=2,
        occurrence_uid="回归本期",
        plan_id=1,
        period_key="2026-09-14",
        generation_scheduled_at=datetime(2026, 9, 15, 14),
        review_scheduled_at=datetime(2026, 9, 15, 15),
        release_scheduled_at=datetime(2026, 9, 15, 16),
        material_scope_json={"mode": "rolling_days", "rolling_days": 14},
    )
    db = AsyncMock()
    db.exec.side_effect = [
        SimpleNamespace(one=lambda: 1),
        SimpleNamespace(all=lambda: [plan]),
        SimpleNamespace(all=lambda: [occurrence]),
    ]
    monkeypatch.setattr(service, "_company_names", AsyncMock(return_value={}))
    result = await service.list_plans(db, page=1, size=20, current_user_id=1, is_admin=True)
    saved = result.items[0].pending_occurrence
    assert saved.period_key == "2026-09-14"
    assert saved.generation_scheduled_at == datetime(2026, 9, 15, 14)
    assert saved.review_scheduled_at == datetime(2026, 9, 15, 15)
    assert saved.release_scheduled_at == datetime(2026, 9, 15, 16)
    assert saved.material_scope.rolling_days == 14


@pytest.mark.asyncio
async def test_changing_date_updates_same_occurrence(monkeypatch):
    service = InsightFeishuBriefService()
    plan = InsightFeishuBriefPlan(id=1, plan_uid="回归计划", plan_name="周报")
    occurrence = InsightFeishuBriefOccurrence(
        id=2,
        occurrence_uid="回归本期",
        plan_id=1,
        period_key="2026-09-14",
        generation_scheduled_at=datetime(2026, 9, 15, 14),
        review_scheduled_at=datetime(2026, 9, 15, 15),
        release_scheduled_at=datetime(2026, 9, 15, 16),
    )
    db = AsyncMock()
    db.add = Mock()
    db.exec.return_value = SimpleNamespace(first=lambda: occurrence)
    monkeypatch.setattr(service, "_require_plan", AsyncMock(return_value=plan))
    payload = InsightFeishuBriefOccurrenceOverride(
        period_key="2026-09-14",
        generation_scheduled_at=datetime(2026, 9, 16, 14),
        review_scheduled_at=datetime(2026, 9, 16, 15),
        release_scheduled_at=datetime(2026, 9, 16, 16),
    )
    saved = await service.upsert_occurrence(db, 1, payload, user_id=1)
    assert saved.id == 2
    assert saved.period_key == "2026-09-14"
    assert saved.generation_scheduled_at == datetime(2026, 9, 16, 14)
    assert db.add.call_args_list[0].args[0] is occurrence
    db.commit.assert_awaited_once()

    occurrence.run_id = 3
    with pytest.raises(ValueError, match="该周期已经生成"):
        await service.upsert_occurrence(db, 1, payload, user_id=1)
