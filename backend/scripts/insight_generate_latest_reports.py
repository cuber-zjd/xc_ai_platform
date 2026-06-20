"""基于最新期初情报生成二次培训报告。

用途：
- 不删除既有报告；
- 显式选择最新正式情报 ID，避免报告仍只引用早期素材；
- 生成健源、御馨、公共主题、AI 深化样本、电商新品等可培训报告。
"""

import argparse
import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightCompany, InsightDataSource, InsightIntelligence, InsightReport, InsightVisibilityRule
from app.models.system.sys_company import SysCompany  # noqa: F401
from app.schemas.agent.insight.report import InsightReportGenerateRequest
from app.services.agent.insight.report_service import insight_report_service


REPORT_CASES = [
    {
        "key": "jianyuan_latest",
        "title": "健源相关企业与行业动态期初运行报告",
        "template_code": "weekly_report",
        "report_type": "市场洞察周报",
        "sys_company_id": 6,
        "max_materials": 80,
        "prompt": "基于最新入库情报，生成面向健源业务培训的市场洞察报告，突出企业经营动态、研发技术、功能糖/食品原料机会、风险和后续跟踪建议。",
    },
    {
        "key": "yuxin_latest",
        "title": "御馨相关竞对与客户机会期初运行报告",
        "template_code": "competitor_dynamic_report",
        "report_type": "竞对动态报告",
        "sys_company_id": 22,
        "max_materials": 80,
        "prompt": "基于最新入库情报，生成面向御馨业务培训的竞对动态报告，突出植物蛋白、客户新品、渠道变化、潜在合作机会和风险提醒。",
    },
    {
        "key": "public_industry",
        "title": "食品饮料与原料行业公共主题简报",
        "template_code": "industry_topic_report",
        "report_type": "行业专题报告",
        "public_only": True,
        "max_materials": 80,
        "prompt": "基于公共主题情报，生成食品饮料、原料、政策和消费趋势的行业专题简报，要求适合培训讲解和后续选题跟踪。",
    },
    {
        "key": "deepened_samples",
        "title": "AI 深化样本洞察与证据质量报告",
        "template_code": "deep_research_report",
        "report_type": "深度研究报告",
        "deepened_only": True,
        "max_materials": 60,
        "prompt": "基于已完成 AI 深化或富化的情报，生成一份深度研究样本报告，展示摘要、标签、情感、机会风险和证据质量如何支撑业务判断。",
    },
    {
        "key": "ecommerce_new_products",
        "title": "电商新品与渠道信号监测报告",
        "template_code": "ecommerce_new_product_monitor",
        "report_type": "电商新品监测报告",
        "source_types": ["ecommerce_search"],
        "max_materials": 80,
        "prompt": "基于电商和新品相关情报，生成新品与渠道信号监测报告；对图片搜索、联盟跳转、验证码等弱证据要明确提示证据局限，不要过度下结论。",
    },
]


async def run(args: argparse.Namespace) -> None:
    engine.echo = False
    generated: list[dict[str, Any]] = []
    async with async_session() as db:
        for case in REPORT_CASES[: args.max_reports]:
            intelligence_ids = await select_intelligence_ids(db, case)
            if len(intelligence_ids) < 5:
                generated.append({"key": case["key"], "status": "skipped", "reason": f"素材不足：{len(intelligence_ids)}"})
                continue
            if args.rules_only:
                async def generate_with_rules(payload, materials, template):
                    return insight_report_service._fallback_content(payload, materials, template), "rules"

                insight_report_service._generate_content = generate_with_rules  # type: ignore[method-assign]

            response = await insight_report_service.generate_report(
                db,
                InsightReportGenerateRequest(
                    title=case["title"],
                    report_type=case["report_type"],
                    template_code=case["template_code"],
                    intelligence_ids=intelligence_ids,
                    folder_name=None,
                    max_materials=min(case["max_materials"], len(intelligence_ids)),
                    generation_prompt=case["prompt"],
                    period_end=datetime.now(),
                ),
                user_id=args.user_id,
                is_admin=True,
            )
            await refresh_report_visibility(db, response.report.id or 0, case)
            generated.append(
                {
                    "key": case["key"],
                    "report_id": response.report.id,
                    "title": response.report.title,
                    "materials": response.used_material_count,
                    "mode": response.generation_mode,
                    "max_material_id": max(intelligence_ids) if intelligence_ids else None,
                }
            )
        active_reports = len((await db.exec(select(InsightReport).where(InsightReport.is_deleted == 0))).all())
        print({"generated": generated, "active_reports": active_reports}, flush=True)


async def select_intelligence_ids(db, case: dict[str, Any]) -> list[int]:
    filters = [InsightIntelligence.is_deleted == 0, InsightIntelligence.status == "active"]
    statement = select(InsightIntelligence.id).order_by(InsightIntelligence.create_time.desc(), InsightIntelligence.id.desc())
    if case.get("sys_company_id"):
        statement = statement.join(InsightCompany, InsightCompany.id == InsightIntelligence.company_id)
        filters.append(InsightCompany.sys_company_id == case["sys_company_id"])
    if case.get("public_only"):
        filters.append(InsightIntelligence.company_id.is_(None))
    if case.get("deepened_only"):
        filters.append(text("raw_payload->>'deepening_status' = 'completed'"))
    if case.get("source_types"):
        statement = statement.join(InsightDataSource, InsightDataSource.id == InsightIntelligence.data_source_id)
        filters.append(InsightDataSource.source_type.in_(case["source_types"]))
    rows = list((await db.exec(statement.where(*filters).limit(case["max_materials"]))).all())
    return [int(row) for row in rows if row]


async def refresh_report_visibility(db, report_id: int, case: dict[str, Any]) -> None:
    report = (await db.exec(select(InsightReport).where(InsightReport.id == report_id))).first()
    if not report:
        return
    report.owner_user_id = None
    sys_company_id = case.get("sys_company_id")
    if sys_company_id:
        report.visibility_scope = "assigned"
        existing = (
            await db.exec(
                select(InsightVisibilityRule).where(
                    InsightVisibilityRule.target_type == "report",
                    InsightVisibilityRule.target_id == report_id,
                    InsightVisibilityRule.principal_type == "sys_company",
                    InsightVisibilityRule.principal_id == sys_company_id,
                    InsightVisibilityRule.permission == "view",
                    InsightVisibilityRule.is_deleted == 0,
                )
            )
        ).first()
        if existing:
            existing.status = "active"
        else:
            db.add(
                InsightVisibilityRule(
                    target_type="report",
                    target_id=report_id,
                    principal_type="sys_company",
                    principal_id=sys_company_id,
                    permission="view",
                    grant_type="bootstrap",
                    status="active",
                )
            )
    else:
        report.visibility_scope = "public"
    await db.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, default=720)
    parser.add_argument("--max-reports", type=int, default=len(REPORT_CASES))
    parser.add_argument("--rules-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
