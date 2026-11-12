"""报告目录与原机器人接收对象，仅提供当前绑定账号可访问的材料。"""
from datetime import datetime
import json
from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.agent.insight import InsightFeishuBriefPlan, InsightFeishuBriefRun, InsightReport
from app.models.agent.insight.workspace import InsightWorkspaceItem
from app.models.system.sys_company import SysCompany
from app.schemas.agent.insight.workspace import ReportInput, ReportQuery
from app.services.agent.insight.permission_service import insight_permission_service
from app.services.agent.insight.workspace_auth import WorkspacePrincipal


async def owned_item(db: AsyncSession, principal: WorkspacePrincipal, item_id: str, kind: str, *, lock: bool = False) -> InsightWorkspaceItem:
    query = select(InsightWorkspaceItem).where(
        InsightWorkspaceItem.id == item_id, InsightWorkspaceItem.scope == principal.scope,
        InsightWorkspaceItem.owner == principal.owner, InsightWorkspaceItem.kind == kind)
    if lock:
        query = query.with_for_update()
    row = (await db.exec(query)).first()
    if not row:
        raise HTTPException(404, "内容不存在或无权访问")
    return row


async def owned_items(db: AsyncSession, principal: WorkspacePrincipal, kind: str) -> list[InsightWorkspaceItem]:
    return list((await db.exec(select(InsightWorkspaceItem).where(
        InsightWorkspaceItem.scope == principal.scope, InsightWorkspaceItem.owner == principal.owner,
        InsightWorkspaceItem.kind == kind).order_by(InsightWorkspaceItem.updated_at.desc()))).all())


async def owned_plans(db: AsyncSession, principal: WorkspacePrincipal) -> list[InsightFeishuBriefPlan]:
    # 机器人目录授权与原计划编辑权限分离。只有部署时显式授权的账号可汇总机器人报告。
    readers = json.loads(settings.INSIGHT_WORKSPACE_BOT_READERS_JSON)
    filters = [InsightFeishuBriefPlan.is_deleted == 0]
    if f"{principal.scope}:{principal.owner}" not in readers:
        filters.append(InsightFeishuBriefPlan.owner_user_id == principal.user_id)
    return list((await db.exec(select(InsightFeishuBriefPlan).where(*filters))).all())


async def recipient_map(db: AsyncSession, principal: WorkspacePrincipal) -> dict[str, dict]:
    result = {}
    for plan in await owned_plans(db, principal):
        for recipient in [*(plan.recipients_json or []), *(plan.afternoon_recipients_json or [])]:
            kind, target = recipient.get("receive_id_type", "open_id"), recipient.get("receive_id", "")
            if target and kind in {"open_id", "user_id", "union_id", "email", "chat_id"}:
                key = f"{kind}:{target}"
                result[key] = {"id": key, "name": recipient.get("name") or f"{plan.plan_name}的既有接收对象",
                               "receive_id_type": kind, "receive_id": target}
    return result


async def options(db: AsyncSession, principal: WorkspacePrincipal) -> dict:
    companies = (await db.exec(select(SysCompany.name).where(SysCompany.is_deleted == 0).order_by(SysCompany.name))).all()
    recipients = await recipient_map(db, principal)
    return {"companies": list(dict.fromkeys(companies)),
            "recipients": [{"id": row["id"], "name": row["name"]} for row in recipients.values()],
            "botName": settings.INSIGHT_FEISHU_BRIEF_BOT_NAME,
            "schedulerReady": bool(settings.INSIGHT_FEISHU_BRIEF_ENABLED)}


def uploaded_record(row: InsightWorkspaceItem) -> dict:
    return {**row.payload, "id": row.id, "date": row.created_at.isoformat(), "source": "uploaded", "canEdit": True}


async def report_catalog(db: AsyncSession, principal: WorkspacePrincipal) -> list[dict]:
    rows = [uploaded_record(row) for row in await owned_items(db, principal, "report")]
    permission = await insight_permission_service.visibility_filter_for_user(
        db, InsightReport, target_type="report", user_id=principal.user_id, is_admin=False)
    # 目录仅查询元数据，不能将报告正文加载到列表或绕开原权限。
    reports = (await db.exec(select(InsightReport.id, InsightReport.title, InsightReport.company_name,
        InsightReport.report_type, InsightReport.summary, InsightReport.create_time).where(
        InsightReport.is_deleted == 0, permission))).all()
    for report in reports:
        rows.append({"id": f"legacy-{report.id}", "title": report.title, "company": report.company_name or "",
            "kind": report.report_type, "summary": report.summary or "", "date": report.create_time.isoformat(),
            "url": f"{settings.INSIGHT_PUBLIC_BASE_URL.rstrip('/')}/insight/reports?report_id={report.id}",
            "source": "generated", "canEdit": False})
    plans = await owned_plans(db, principal)
    if plans:
        plan_map = {plan.id: plan for plan in plans}
        company_ids = [plan.sys_company_id for plan in plans if plan.sys_company_id]
        companies = dict((await db.exec(select(SysCompany.id, SysCompany.name).where(SysCompany.id.in_(company_ids)))).all()) if company_ids else {}
        runs = (await db.exec(select(InsightFeishuBriefRun.id, InsightFeishuBriefRun.plan_id,
            InsightFeishuBriefRun.report_title, InsightFeishuBriefRun.document_url, InsightFeishuBriefRun.create_time).where(
            InsightFeishuBriefRun.plan_id.in_(list(plan_map)), InsightFeishuBriefRun.is_deleted == 0,
            InsightFeishuBriefRun.document_url.is_not(None)))).all()
        for run in runs:
            plan = plan_map[run.plan_id]
            rows.append({"id": f"brief-{run.id}", "title": run.report_title or plan.plan_name,
                "company": companies.get(plan.sys_company_id, ""), "kind": "月报" if plan.schedule_frequency == "monthly" else "周报",
                "summary": "原平台生成的飞书报告，点击直接打开原文档。", "date": run.create_time.isoformat(),
                "url": run.document_url, "source": "generated", "canEdit": False})
    return sorted(rows, key=lambda row: (row["date"], row["id"]), reverse=True)


async def list_reports(db: AsyncSession, principal: WorkspacePrincipal, query: ReportQuery) -> dict:
    rows = await report_catalog(db, principal)
    keyword = query.keyword.casefold()
    rows = [row for row in rows if (not keyword or keyword in f"{row['title']} {row['summary']}".casefold())
        and (not query.company or row["company"] == query.company)
        and (not query.source or row["source"] == query.source)
        and (not query.kind or row["kind"] == query.kind)]
    start = (query.page - 1) * query.size
    return {"items": rows[start:start + query.size], "total": len(rows), "page": query.page, "size": query.size}


async def save_report(db: AsyncSession, principal: WorkspacePrincipal, body: ReportInput) -> dict:
    row = await owned_item(db, principal, body.id, "report") if body.id else InsightWorkspaceItem(
        scope=principal.scope, owner=principal.owner, legacy_user_id=principal.user_id, kind="report")
    row.payload = body.model_dump(exclude={"id"})
    row.updated_at = datetime.now()
    db.add(row)
    await db.commit()
    return uploaded_record(row)
