"""仅归档当前工作空间自己的记录，保留原文档与执行审计。"""
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from app.schemas.agent.insight.workspace import ArchiveInput
from app.services.agent.insight.workspace_auth import WorkspacePrincipal
from app.services.agent.insight.workspace_catalog import owned_item, owned_items
from app.services.agent.insight.monitor_config_service import insight_monitor_config_service


async def archive(db: AsyncSession, principal: WorkspacePrincipal, body: ArchiveInput) -> dict:
    row = await owned_item(db, principal, body.id, body.kind, lock=True)
    if row.last_status in {"queued", "sending"}:
        raise HTTPException(409, "发送正在处理，暂不能归档")
    if body.kind == "collection":
        await insight_monitor_config_service.delete_config(db, row.payload["legacyId"], principal.user_id, is_admin=False)
    if body.kind == "report":
        plans = [plan for plan in await owned_items(db, principal, "push") if plan.payload["reportId"] == row.id]
        if any(plan.last_status in {"queued", "sending"} for plan in plans):
            raise HTTPException(409, "报告正在推送，暂不能归档")
        for plan in plans:
            plan.enabled = False
            plan.next_run = None
            plan.last_message = "关联报告已归档，定时推送已暂停"
            db.add(plan)
    row.kind = f"archived_{body.kind}"
    row.enabled = False
    row.next_run = None
    db.add(row)
    await db.commit()
    return {"archived": True}
