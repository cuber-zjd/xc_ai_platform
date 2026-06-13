import asyncio
from datetime import datetime

from sqlalchemy import func
from sqlmodel import SQLModel, select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightCompany, InsightReport, InsightReportMaterial, InsightReportVersion
from app.models.system.sys_model import SysModel
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.report import InsightReportGenerateRequest
from app.services.agent.insight.report_service import insight_report_service


REPORT_CASES = [
    {
        "title": "四企业市场洞察深度研究报告",
        "report_type": "专题报告",
        "company_codes": [],
        "max_materials": 100,
        "generation_prompt": "生成一份可直接交付给内部客户经营团队阅读的 Word 式深度研究报告，覆盖茶百道、蜜雪冰城、可口可乐、汤臣倍健。这些企业在本测试用例中均按我们的客户或潜在客户处理。正文要完整分析企业动态、新品、渠道、竞争、供应链、风险和合作机会；表达应服务客户维护、销售跟进和方案匹配，不要展示思考过程；引用必须可追溯。",
    },
    {
        "title": "茶饮企业客户动态与竞争策略研究报告",
        "report_type": "企业动态报告",
        "company_codes": ["p1_chabaidao", "p1_mixue"],
        "max_materials": 90,
        "generation_prompt": "生成一份 Word 式客户经营研究报告，聚焦茶百道、蜜雪冰城的门店、出海、价格带、营销活动、新品和竞品动作。这些企业按我们的客户或潜在客户处理。要求段落化叙述，结论克制，突出客户维护、销售跟进、合作机会和方案匹配意义。",
    },
    {
        "title": "饮料与营养健康市场机会研究报告",
        "report_type": "专题报告",
        "company_codes": ["p1_cocacola", "p1_byhealth"],
        "max_materials": 90,
        "generation_prompt": "生成一份 Word 式客户经营研究报告，聚焦可口可乐、汤臣倍健相关的饮料创新、营养健康、渠道变化、科研背书、品牌合作和潜在风险。这些企业按我们的客户或潜在客户处理。正文要有行业判断、客户经营含义、合作机会和后续跟踪建议。",
    },
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as db:
        user_id = await first_user_id(db)
        models = await enabled_models(db)
        deleted = await soft_delete_existing_reports(db, user_id=user_id)
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
                    "has_chapters": bool(response.report.content_json.get("chapters")),
                    "chapter_count": len(response.report.content_json.get("chapters") or []),
                }
            )

        active_reports = (await db.exec(select(func.count()).select_from(InsightReport).where(InsightReport.is_deleted == 0))).one()
        active_materials = (await db.exec(select(func.count()).select_from(InsightReportMaterial).where(InsightReportMaterial.is_deleted == 0))).one()
        print(
            {
                "user_id": user_id,
                "advanced_models": models,
                "soft_deleted": deleted,
                "generated": generated,
                "active_reports": active_reports,
                "active_report_materials": active_materials,
            }
        )


async def soft_delete_existing_reports(db, *, user_id: int) -> dict[str, int]:
    reports = list((await db.exec(select(InsightReport).where(InsightReport.is_deleted == 0))).all())
    report_ids = [row.id for row in reports if row.id]
    materials = list((await db.exec(select(InsightReportMaterial).where(InsightReportMaterial.report_id.in_(report_ids)))).all()) if report_ids else []
    versions = list((await db.exec(select(InsightReportVersion).where(InsightReportVersion.report_id.in_(report_ids)))).all()) if report_ids else []

    for report in reports:
        report.is_deleted = 1
        report.status = "deleted"
        report.update_by = str(user_id)
        report.update_time = datetime.now()
    for material in materials:
        material.is_deleted = 1
        material.update_by = str(user_id)
        material.update_time = datetime.now()
    for version in versions:
        version.is_deleted = 1
        version.update_by = str(user_id)
        version.update_time = datetime.now()
    await db.commit()
    return {"reports": len(reports), "materials": len(materials), "versions": len(versions)}


async def first_user_id(db) -> int:
    user = (await db.exec(select(SysUser).where(SysUser.is_deleted == 0).order_by(SysUser.id.asc()).limit(1))).first()
    return user.id if user and user.id else 1


async def company_id_map(db) -> dict[str, int]:
    rows = list((await db.exec(select(InsightCompany).where(InsightCompany.is_deleted == 0))).all())
    return {row.company_code: row.id or 0 for row in rows}


async def enabled_models(db) -> list[tuple[str, int, str | None]]:
    rows = list(
        (
            await db.exec(
                select(SysModel)
                .where(SysModel.is_enabled == True, SysModel.status == 1, SysModel.model_type == "chat")  # noqa: E712
                .order_by(SysModel.model_level.asc(), SysModel.priority.asc())
            )
        ).all()
    )
    return [(row.model_name, row.model_level, row.capability) for row in rows]


if __name__ == "__main__":
    asyncio.run(main())
