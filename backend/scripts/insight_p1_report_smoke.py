import asyncio
from datetime import datetime

from sqlalchemy import func
from sqlmodel import SQLModel, select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightCompany, InsightReport, InsightReportMaterial, InsightUserIntelligencePool
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.report import InsightReportGenerateRequest
from app.services.agent.insight.report_service import insight_report_service


REPORT_CASES = [
    {
        "title": "P1测试-四企业市场洞察专题报告",
        "report_type": "专题报告",
        "company_codes": [],
        "max_materials": 80,
        "generation_prompt": "覆盖茶百道、蜜雪冰城、可口可乐、汤臣倍健，提炼新品、经营、市场扩张、供应链和风险机会。",
    },
    {
        "title": "P1测试-茶饮客户动态报告",
        "report_type": "企业动态报告",
        "company_codes": ["p1_chabaidao", "p1_mixue"],
        "max_materials": 70,
        "generation_prompt": "聚焦茶饮企业的门店、出海、价格带、竞品动作和新品营销。",
    },
    {
        "title": "P1测试-饮料与营养健康机会报告",
        "report_type": "专题报告",
        "company_codes": ["p1_cocacola", "p1_byhealth"],
        "max_materials": 70,
        "generation_prompt": "聚焦饮料和营养健康行业的产品创新、合作投资、科研背书和渠道变化。",
    },
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as db:
        user_id = await first_user_id(db)
        pool_count = (
            await db.exec(
                select(func.count()).select_from(InsightUserIntelligencePool).where(
                    InsightUserIntelligencePool.user_id == user_id,
                    InsightUserIntelligencePool.pool_type == "report_material",
                    InsightUserIntelligencePool.is_deleted == 0,
                    InsightUserIntelligencePool.status == "active",
                )
            )
        ).one()
        company_map = await company_id_map(db)
        generated = []
        for case in REPORT_CASES:
            company_ids = [company_map[code] for code in case["company_codes"] if code in company_map]
            response = await insight_report_service.generate_report(
                db,
                InsightReportGenerateRequest(
                    title=case["title"],
                    report_type=case["report_type"],
                    company_ids=company_ids,
                    folder_name="P1企业档案测试素材",
                    max_materials=case["max_materials"],
                    generation_prompt=case["generation_prompt"],
                    period_end=datetime.now(),
                ),
                user_id=user_id,
                is_admin=True,
            )
            generated.append(
                {
                    "id": response.report.id,
                    "title": response.report.title,
                    "materials": response.used_material_count,
                    "mode": response.generation_mode,
                }
            )

        report_count = (await db.exec(select(func.count()).select_from(InsightReport).where(InsightReport.is_deleted == 0))).one()
        material_count = (await db.exec(select(func.count()).select_from(InsightReportMaterial).where(InsightReportMaterial.is_deleted == 0))).one()
        print(
            {
                "user_id": user_id,
                "report_material_pool": pool_count,
                "generated": generated,
                "total_reports": report_count,
                "total_report_materials": material_count,
            }
        )


async def first_user_id(db) -> int:
    user = (await db.exec(select(SysUser).where(SysUser.is_deleted == 0).order_by(SysUser.id.asc()).limit(1))).first()
    return user.id if user and user.id else 1


async def company_id_map(db) -> dict[str, int]:
    rows = list((await db.exec(select(InsightCompany).where(InsightCompany.is_deleted == 0))).all())
    return {row.company_code: row.id or 0 for row in rows}


if __name__ == "__main__":
    asyncio.run(main())
