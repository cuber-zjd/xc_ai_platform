from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import InsightFeishuBriefPlan, InsightFeishuBriefRun
from app.models.system.sys_company import SysCompany
from app.services.agent.insight.feishu_brief_service import (
    insight_feishu_brief_service,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="整理飞书简报文档目录")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际创建目录并移动文档；不传时只输出整理计划",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="最多扫描的简报执行记录数",
    )
    return parser.parse_args()


async def run(*, apply: bool, limit: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "mode": "apply" if apply else "preview",
        "checked_runs": 0,
        "moved_documents": 0,
        "skipped_documents": 0,
        "failed_documents": 0,
        "items": [],
    }
    moved_tokens: set[str] = set()
    async with async_session() as db:
        runs = list(
            (
                await db.exec(
                    select(InsightFeishuBriefRun)
                    .where(
                        InsightFeishuBriefRun.is_deleted == 0,
                        InsightFeishuBriefRun.document_id.is_not(None),
                    )
                    .order_by(InsightFeishuBriefRun.id.asc())
                    .limit(max(1, min(limit, 5000)))
                )
            ).all()
        )
        plan_ids = {row.plan_id for row in runs}
        plans = {
            row.id: row
            for row in (
                await db.exec(
                    select(InsightFeishuBriefPlan).where(
                        InsightFeishuBriefPlan.id.in_(plan_ids)
                    )
                )
            ).all()
        }
        company_ids = {
            row.sys_company_id
            for row in plans.values()
            if row.sys_company_id is not None
        }
        companies = {
            row.id: row
            for row in (
                await db.exec(
                    select(SysCompany).where(SysCompany.id.in_(company_ids))
                )
            ).all()
        }
        for brief_run in runs:
            report["checked_runs"] += 1
            plan = plans.get(brief_run.plan_id)
            company = companies.get(plan.sys_company_id) if plan else None
            if not plan or not company:
                report["failed_documents"] += 1
                report["items"].append(
                    {
                        "run_id": brief_run.id,
                        "status": "failed",
                        "error": "未找到简报计划或所属公司",
                    }
                )
                continue
            documents: list[tuple[str, str, str]] = [
                (str(brief_run.document_id), "final", brief_run.report_title or "正式稿")
            ]
            for artifact in (brief_run.output_payload or {}).get("artifacts") or []:
                document_id = str(artifact.get("document_id") or "")
                if document_id:
                    documents.append(
                        (
                            document_id,
                            "process",
                            str(artifact.get("title") or "生成过程"),
                        )
                    )
            for document_id, artifact_type, title in documents:
                if document_id in moved_tokens:
                    report["skipped_documents"] += 1
                    continue
                moved_tokens.add(document_id)
                target_path = (
                    f"{insight_feishu_brief_service._short_company_name(company.name)}/"
                    f"{brief_run.period_end.year}年/"
                    f"{'月报' if plan.schedule_frequency == 'monthly' else '日报' if plan.schedule_frequency == 'daily' else '周报'}"
                )
                if plan.schedule_frequency == "monthly":
                    target_path += "/生成过程" if artifact_type == "process" else "/正式稿"
                item = {
                    "run_id": brief_run.id,
                    "document_id": document_id,
                    "title": title,
                    "target_path": target_path,
                }
                if not apply:
                    item["status"] = "planned"
                    report["items"].append(item)
                    continue
                try:
                    folder = await insight_feishu_brief_service._resolve_document_folder(
                        company_name=company.name,
                        frequency=plan.schedule_frequency,
                        period_end=brief_run.period_end,
                        artifact_type=artifact_type,
                    )
                    if not folder.organized:
                        raise ValueError(folder.warning or "无法创建目标目录")
                    await insight_feishu_brief_service.move_document_to_folder(
                        document_id,
                        folder.token,
                    )
                    item["status"] = "moved"
                    item["folder_token"] = folder.token
                    report["moved_documents"] += 1
                except Exception as exc:
                    item["status"] = "failed"
                    item["error"] = str(exc)[:500]
                    report["failed_documents"] += 1
                report["items"].append(item)
    return report


async def main() -> None:
    args = parse_args()
    report = await run(apply=args.apply, limit=args.limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
