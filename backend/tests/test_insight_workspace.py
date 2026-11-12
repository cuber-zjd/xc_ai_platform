"""隔离数据库与外部机器人，不向真实接收对象发送测试消息。"""
import hashlib
import hmac
import json
import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app.core.config import settings
from app.models.agent.insight.workspace import InsightWorkspaceItem
from app.models.agent.insight import InsightMonitorConfig, InsightChannel
from app.schemas.agent.insight.workspace import ReportInput, CollectionInput, PushInput, PushAction, normalize_document_url
from app.services.agent.insight import workspace_auth as auth, workspace_catalog as catalog, workspace_pushes as pushes
from app.services.agent.insight import workspace_collections as collections
from app.schemas.agent.insight.workspace import CollectionStatus
from app.schemas.agent.insight.workspace import ArchiveInput
from app.services.agent.insight.workspace_archive import archive

P = auth.WorkspacePrincipal("tenant:app", "owner", 720)

@compiles(JSONB, "sqlite")
def compile_jsonb_for_isolated_tests(type_, compiler, **kwargs):
    return "JSON"

@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: SQLModel.metadata.create_all(conn, tables=[InsightWorkspaceItem.__table__, InsightMonitorConfig.__table__, InsightChannel.__table__]))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()

@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://feishu.cn/docx/Abc", "https://feishu.cn.evil.test/docx/Abc", "https://x.feishu.cn@evil.test/docx/Abc", "https://feishu.cn/docx/Abc/extra", "https://feishu.cn:444/docx/Abc"])
def test_reject_unsafe_document_url(url):
    with pytest.raises(ValueError):
        normalize_document_url(url)

def test_strip_credentials_from_document_link():
    assert normalize_document_url("https://xiangchi.feishu.cn/docx/Abc?disposable_login_token=secret#section") == "https://xiangchi.feishu.cn/docx/Abc"

@pytest.mark.parametrize("frequency,expected", [("weekly", "2026-11-16T09:00:00"), ("once", "2026-11-13T09:00:00")])
def test_schedule_uses_shanghai(frequency, expected):
    payload = PushInput(reportId="r", recipientIds=["user_id:x"], frequency=frequency, weekday=1, time="09:00", scheduledAt="2026-11-13T01:00:00Z").model_dump()
    now = datetime(2026, 11, 12, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert pushes.next_schedule(payload, now).isoformat() == expected

def test_past_single_schedule_is_rejected():
    payload = PushInput(reportId="r", recipientIds=["user_id:x"], scheduledAt="2020-01-01T09:00:00+08:00").model_dump()
    with pytest.raises(HTTPException) as error:
        pushes.next_schedule(payload)
    assert error.value.status_code == 422

def test_collection_input_validation():
    with pytest.raises(ValueError):
        CollectionInput(need="12345", name="name", keywords=["x" * 101])
    with pytest.raises(ValueError):
        PushInput(reportId="r", recipientIds=["x"], time="25:80")

@pytest.mark.asyncio
async def test_save_report_roundtrip_and_scope_isolation(db):
    saved = await catalog.save_report(db, P, ReportInput(title="需求报告", company="另一家公司", url="https://example.feishu.cn/docx/Abc"))
    row = await catalog.owned_item(db, P, saved["id"], "report")
    assert row.payload["company"] == "另一家公司"
    for who in [auth.WorkspacePrincipal("other:app", "owner", 720), auth.WorkspacePrincipal("tenant:app", "other", 720)]:
        with pytest.raises(HTTPException) as error:
            await catalog.owned_item(db, who, row.id, "report")
        assert error.value.status_code == 404

@pytest.fixture
def sender(monkeypatch):
    monkeypatch.setattr(settings, "INSIGHT_FEISHU_BRIEF_ENABLED", True)
    monkeypatch.setattr(pushes, "report_catalog", AsyncMock(return_value=[{"id": "r", "title": "报告", "url": "https://example.feishu.cn/docx/Abc"}]))
    monkeypatch.setattr(pushes, "recipient_map", AsyncMock(return_value={"user_id:x": {"id": "user_id:x", "name": "已有对象"}}))
    request = AsyncMock(return_value={"message_id": "fake"})
    monkeypatch.setattr(pushes.insight_feishu_brief_service, "_request", request)
    return request

@pytest.mark.asyncio
async def test_push_save_is_draft_and_no_send(db, sender):
    result = await pushes.save_push(db, P, PushInput(reportId="r", recipientIds=["user_id:x"]))
    assert result["lastStatus"] == "draft" and not result["enabled"]
    sender.assert_not_called()


@pytest.mark.asyncio
async def test_edit_pauses_push_and_archive_preserves_audit(db, sender):
    saved = await pushes.save_push(db, P, PushInput(reportId="r", recipientIds=["user_id:x"], frequency="weekly"))
    await pushes.perform_action(db, P, PushAction(id=saved["id"], action="status", active=True, confirmed=True))
    edited = await pushes.save_push(db, P, PushInput(id=saved["id"], reportId="r", recipientIds=["user_id:x"], time="10:00"))
    assert not edited["enabled"] and edited["nextRun"] is None
    assert edited["lastStatus"] == "draft"
    await archive(db, P, ArchiveInput(id=saved["id"], kind="push"))
    assert not await catalog.owned_items(db, P, "push")
    assert len(await catalog.owned_items(db, P, "archived_push")) == 1
    sender.assert_not_called()


@pytest.mark.asyncio
async def test_cannot_archive_queued_push(db, sender):
    saved = await pushes.save_push(db, P, PushInput(reportId="r", recipientIds=["user_id:x"]))
    await pushes.perform_action(db, P, PushAction(id=saved["id"], action="send", confirmed=True, requestId="c" * 32))
    with pytest.raises(HTTPException) as error:
        await archive(db, P, ArchiveInput(id=saved["id"], kind="push"))
    assert error.value.status_code == 409
    sender.assert_not_called()

@pytest.mark.asyncio
async def test_unapproved_recipient_rejected(db, sender):
    with pytest.raises(HTTPException) as error:
        await pushes.save_push(db, P, PushInput(reportId="r", recipientIds=["chat_id:other"]))
    assert error.value.status_code == 403
    sender.assert_not_called()

@pytest.mark.asyncio
async def test_preview_no_send_and_send_idempotent(db, sender):
    row = await pushes.save_push(db, P, PushInput(reportId="r", recipientIds=["user_id:x"]))
    card = await pushes.perform_action(db, P, PushAction(id=row["id"], action="preview"))
    assert card["recipients"][0]["name"] == "已有对象"
    sender.assert_not_called()
    action = PushAction(id=row["id"], action="send", confirmed=True, requestId="a" * 32)
    first = await pushes.perform_action(db, P, action)
    second = await pushes.perform_action(db, P, action)
    assert first["lastStatus"] == second["lastStatus"] == "queued"
    sender.assert_not_called()
    record = await catalog.owned_item(db, P, row["id"], "push")
    await pushes.deliver(db, record, card)
    assert sender.await_count == 1
    assert sender.call_args.kwargs["json"]["uuid"]

@pytest.mark.asyncio
async def test_unknown_send_result_pauses_without_retry(db, sender):
    sender.side_effect = TimeoutError()
    row = await pushes.save_push(db, P, PushInput(reportId="r", recipientIds=["user_id:x"]))
    await pushes.perform_action(db, P, PushAction(id=row["id"], action="send", confirmed=True, requestId="a" * 32))
    record = await catalog.owned_item(db, P, row["id"], "push")
    result = await pushes.deliver(db, record, await pushes.preview(db, P, record.payload))
    assert result["lastStatus"] == "uncertain" and not result["enabled"]
    with pytest.raises(HTTPException) as error:
        await pushes.perform_action(db, P, PushAction(id=row["id"], action="send", confirmed=True, requestId="b" * 32))
    assert error.value.status_code == 409
    assert sender.await_count == 1

@pytest.mark.asyncio
async def test_send_requires_confirmation(db, sender):
    row = await pushes.save_push(db, P, PushInput(reportId="r", recipientIds=["user_id:x"]))
    with pytest.raises(HTTPException):
        await pushes.perform_action(db, P, PushAction(id=row["id"], action="send"))
    sender.assert_not_called()

@pytest.mark.asyncio
async def test_signature_binds_body_path_principal_and_expiry(monkeypatch):
    secret = "s" * 40
    monkeypatch.setattr(settings, "INSIGHT_WORKSPACE_KEY", secret)
    monkeypatch.setattr(settings, "INSIGHT_WORKSPACE_BINDINGS_JSON", json.dumps({P.scope: {P.owner: P.user_id}}))
    db = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(first=lambda: object())))
    body, stamp = b"{}", str(int(time.time() * 1000))
    principal = f"{P.scope}:{P.owner}"
    signature = hmac.new(secret.encode(), f"{stamp}\n{principal}\nPOST\n/options\n{{}}".encode(), hashlib.sha256).hexdigest()
    async def check(actual_body=body, actual_path="/options", actual_stamp=stamp, actual_principal=principal):
        async def receive():
            return {"type": "http.request", "body": actual_body}
        request = Request({"type": "http", "method": "POST", "path": f"/ai-api/v1/insight-workspace{actual_path}",
            "headers": [(b"x-workspace-time", actual_stamp.encode()), (b"x-workspace-principal", actual_principal.encode()), (b"x-workspace-signature", signature.encode())]}, receive)
        return await auth.authenticate(request, db)
    assert await check() == P
    for args in [{"actual_body": b'{"user":1}'}, {"actual_path": "/pushes/action"}, {"actual_stamp": "0"}, {"actual_principal": "other:app:owner"}]:
        with pytest.raises(HTTPException) as error:
            await check(**args)
        assert error.value.status_code == 401

@pytest.mark.asyncio
async def test_collection_real_service_save_enable_pause_and_edit(db):
    draft = CollectionInput(need="关注其他行业的新产品公告", name="新品观察", company="新公司", keywords=["新产品"], excluded=["招聘"])
    row = await collections.save_collection(db, P, draft)
    assert row["status"] == "paused" and row["nextRun"] is None
    active = await collections.set_status(db, P, CollectionStatus(id=row["id"], active=True))
    assert active["status"] == "active" and active["nextRun"]
    edited = await collections.save_collection(db, P, CollectionInput(**{**draft.model_dump(), "id": row["id"], "name": "修改后的需求"}))
    assert edited["status"] == "paused" and edited["nextRun"] is None
    loaded = await collections.list_collections(db, P)
    assert len(loaded) == 1 and loaded[0]["name"] == "修改后的需求"
    assert loaded[0]["company"] == "新公司"
    with pytest.raises(HTTPException) as error:
        await collections.set_status(db, auth.WorkspacePrincipal("other:app", "owner", 720), CollectionStatus(id=row["id"], active=True))
    assert error.value.status_code == 404

@pytest.mark.asyncio
async def test_queue_worker_and_revoked_user(db, sender, monkeypatch):
    monkeypatch.setattr(settings, "INSIGHT_WORKSPACE_KEY", "s" * 40)
    monkeypatch.setattr(settings, "INSIGHT_WORKSPACE_BINDINGS_JSON", json.dumps({P.scope: {P.owner: P.user_id}}))
    original_get = db.get
    async def get(model, identity, **kwargs):
        if model is pushes.SysUser:
            return SimpleNamespace(status=1, is_deleted=0)
        return await original_get(model, identity, **kwargs)
    monkeypatch.setattr(db, "get", get)
    row = await pushes.save_push(db, P, PushInput(reportId="r", recipientIds=["user_id:x"]))
    await pushes.perform_action(db, P, PushAction(id=row["id"], action="send", confirmed=True, requestId="a" * 32))
    await pushes.run_due(db)
    await pushes.run_due(db)
    assert sender.await_count == 1
    assert (await catalog.owned_item(db, P, row["id"], "push")).last_status == "sent"
    assert len(await catalog.owned_items(db, P, "delivery")) == 1
    await pushes.perform_action(db, P, PushAction(id=row["id"], action="send", confirmed=True, requestId="b" * 32))
    monkeypatch.setattr(settings, "INSIGHT_WORKSPACE_BINDINGS_JSON", "{}")
    await pushes.run_due(db)
    assert sender.await_count == 1
    assert (await catalog.owned_item(db, P, row["id"], "push")).last_status == "failed"
