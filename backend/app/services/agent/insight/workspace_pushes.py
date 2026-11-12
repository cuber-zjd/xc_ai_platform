"""已有云文档推送；草稿、预览、启用、执行分离，重试必须显式发起。"""
import json
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.agent.insight.workspace import InsightWorkspaceItem
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.workspace import PushAction, PushInput, normalize_document_url
from app.services.agent.insight.feishu_brief_service import insight_feishu_brief_service
from app.services.agent.insight.workspace_auth import WorkspacePrincipal
from app.services.agent.insight.workspace_catalog import owned_item, owned_items, recipient_map, report_catalog

TZ = ZoneInfo("Asia/Shanghai")


def next_schedule(payload: dict, now: datetime | None = None) -> datetime:
    now = now or datetime.now(TZ)
    if payload["frequency"] == "once":
        if not payload["scheduledAt"]:
            raise HTTPException(422, "请填写定时推送时间，立即发送可直接点击发送按钮。")
        target = datetime.fromisoformat(payload["scheduledAt"].replace("Z", "+00:00")).astimezone(TZ)
        if target <= now:
            raise HTTPException(422, "推送时间必须晚于当前时间")
    else:
        hour, minute = map(int, payload["time"].split(":"))
        # UI与协议：0=周日；Python weekday：0=周一。
        days = (payload["weekday"] - (now.weekday() + 1) % 7) % 7
        target = (now + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=7)
    return target.replace(tzinfo=None)


def push_record(row: InsightWorkspaceItem) -> dict:
    return {**row.payload, "id": row.id, "enabled": row.enabled,
        "nextRun": row.next_run.isoformat() + "+08:00" if row.next_run else None,
        "lastStatus": row.last_status, "lastMessage": row.last_message}


async def preview(db: AsyncSession, principal: WorkspacePrincipal, payload: dict) -> dict:
    reports = await report_catalog(db, principal)
    report = next((item for item in reports if item["id"] == payload["reportId"]), None)
    if not report:
        raise HTTPException(404, "报告不存在或已无权访问")
    try:
        url = normalize_document_url(report["url"])
    except ValueError:
        raise HTTPException(422, "该报告尚无飞书云文档链接，请先添加云文档报告后推送。") from None
    allowed = await recipient_map(db, principal)
    ids = list(dict.fromkeys(payload["recipientIds"]))
    if not ids or any(key not in allowed for key in ids):
        raise HTTPException(403, "接收对象不在当前账号已有推送范围内，请刷新后重新选择。")
    return {"title": report["title"], "url": url,
            "recipients": [{"id": key, "name": allowed[key]["name"]} for key in ids],
            "message": "点击查看报告全文。文档访问权限沿用飞书原有设置；本次推送不会修改文档权限。"}


async def list_pushes(db: AsyncSession, principal: WorkspacePrincipal) -> list[dict]:
    return [push_record(row) for row in await owned_items(db, principal, "push")]


async def save_push(db: AsyncSession, principal: WorkspacePrincipal, body: PushInput) -> dict:
    draft = body.model_dump()
    card = await preview(db, principal, draft)
    row = InsightWorkspaceItem(scope=principal.scope, owner=principal.owner, legacy_user_id=principal.user_id,
        kind="push", payload={**draft, "title": card["title"]}, last_status="draft")
    db.add(row)
    await db.commit()
    return push_record(row)


async def perform_action(db: AsyncSession, principal: WorkspacePrincipal, body: PushAction) -> dict:
    row = await owned_item(db, principal, body.id, "push", lock=body.action != "preview")
    if body.action == "preview":
        return await preview(db, principal, row.payload)
    if body.action == "status":
        if row.last_status in {"queued", "sending"}:
            raise HTTPException(409, "本次发送正在处理，请稍后查看结果")
        if body.active:
            if not body.confirmed:
                raise HTTPException(422, "请先确认接收对象与定时设置")
            if not settings.INSIGHT_FEISHU_BRIEF_ENABLED:
                raise HTTPException(503, "原机器人调度器尚未启用，不能启用定时推送")
            await preview(db, principal, row.payload)
            row.next_run = next_schedule(row.payload)
        else:
            row.next_run = None
        row.enabled = body.active
        row.updated_at = datetime.now()
        db.add(row)
        await db.commit()
        return push_record(row)
    if not body.confirmed or not body.requestId:
        raise HTTPException(422, "发送前必须确认预览及接收对象")
    if row.request_id == body.requestId:
        return push_record(row)
    if row.last_status in {"queued", "sending", "uncertain"}:
        raise HTTPException(409, "上次发送结果尚未确认，请先检查机器人消息，避免重复发送。")
    if not settings.INSIGHT_FEISHU_BRIEF_ENABLED:
        raise HTTPException(503, "原机器人调度器尚未启用")
    await preview(db, principal, row.payload)
    row.request_id = body.requestId
    row.last_status = "queued"
    row.last_message = "已加入推送队列，通常1分钟内执行"
    row.updated_at = datetime.now()
    db.add(row)
    await db.commit()
    return push_record(row)


async def deliver(db: AsyncSession, row: InsightWorkspaceItem, card: dict) -> dict:
    successes = 0
    results = []
    # 不自动补发：网络中断时无法确定接收端是否已收到，保留不确定状态。
    for recipient in card["recipients"]:
        kind, target = recipient["id"].split(":", 1)
        try:
            response = await insight_feishu_brief_service._request("POST", "/open-apis/im/v1/messages",
                params={"receive_id_type": kind}, json={"receive_id": target, "msg_type": "interactive",
                "uuid": str(uuid5(NAMESPACE_URL, f"{row.id}:{row.request_id}:{recipient['id']}")),
                "content": json.dumps({"config": {"wide_screen_mode": True},
                    "header": {"template": "blue", "title": {"tag": "plain_text", "content": card["title"]}},
                    "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": card["message"]}},
                    {"tag": "action", "actions": [{"tag": "button", "text": {"tag": "plain_text", "content": "查看报告"},
                        "type": "primary", "url": card["url"]}]}]}, ensure_ascii=False)})
            successes += 1
            results.append({"recipient": recipient["name"], "status": "sent", "messageId": response.get("message_id")})
        except Exception:
            results.append({"recipient": recipient["name"], "status": "uncertain"})
            row.last_status = "uncertain"
            row.last_message = f"已确认成功 {successes}/{len(card['recipients'])} 个对象，其余结果待核对；已暂停自动推送。"
            row.enabled = False
            row.next_run = None
            break
    else:
        row.last_status = "sent"
        row.last_message = f"已成功发送给 {successes} 个对象"
        if row.enabled and row.payload["frequency"] == "weekly":
            row.next_run = next_schedule(row.payload)
        else:
            row.enabled = False
            row.next_run = None
    row.updated_at = datetime.now()
    db.add(row)
    db.add(InsightWorkspaceItem(scope=row.scope, owner=row.owner, legacy_user_id=row.legacy_user_id,
        kind="delivery", payload={"pushId": row.id, "requestId": row.request_id, "title": card["title"],
        "results": results}, last_status=row.last_status, last_message=row.last_message))
    await db.commit()
    return push_record(row)


async def run_due(db: AsyncSession) -> None:
    if not settings.INSIGHT_WORKSPACE_KEY:
        return
    stale = (await db.exec(select(InsightWorkspaceItem).where(
        InsightWorkspaceItem.kind == "push", InsightWorkspaceItem.last_status == "sending",
        InsightWorkspaceItem.updated_at < datetime.now() - timedelta(minutes=10))
        .with_for_update(skip_locked=True))).all()
    for item in stale:
        item.enabled = False
        item.next_run = None
        item.last_status = "uncertain"
        item.last_message = "发送处理已中断，结果待人工核对；不会自动重发。"
        db.add(item)
    if stale:
        await db.commit()
    # 逐个领取；多进程使用数据库行锁，领取后立即提交，再做外部 I/O。
    for _ in range(20):
        row = (await db.exec(select(InsightWorkspaceItem).where(InsightWorkspaceItem.kind == "push",
            (InsightWorkspaceItem.last_status == "queued") | (
                InsightWorkspaceItem.enabled.is_(True) & (InsightWorkspaceItem.next_run <= datetime.now()) &
                (InsightWorkspaceItem.last_status != "sending"))).order_by(InsightWorkspaceItem.next_run)
            .with_for_update(skip_locked=True).limit(1))).first()
        if not row:
            break
        principal = WorkspacePrincipal(row.scope, row.owner, row.legacy_user_id)
        try:
            # 每次执行重新校验绑定和旧计划接收对象，移除授权后不能继续发送。
            bindings = json.loads(settings.INSIGHT_WORKSPACE_BINDINGS_JSON)
            if bindings.get(row.scope, {}).get(row.owner) != row.legacy_user_id:
                raise HTTPException(403, "账号关联权限已变更")
            user = await db.get(SysUser, row.legacy_user_id)
            if not user or user.status != 1 or user.is_deleted:
                raise HTTPException(403, "关联账号已停用")
            card = await preview(db, principal, row.payload)
        except HTTPException as error:
            row.enabled = False
            row.next_run = None
            row.last_status = "failed"
            row.last_message = str(error.detail)
            db.add(row)
            await db.commit()
            continue
        if row.last_status != "queued":
            row.request_id = f"scheduled:{row.next_run.isoformat()}"
        row.last_status = "sending"
        row.updated_at = datetime.now()
        db.add(row)
        await db.commit()
        await deliver(db, row, card)
