import asyncio

from sqlalchemy import func
from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import (
    InsightCompany,
    InsightDataSource,
    InsightIntelligence,
    InsightIntelligenceCandidate,
    InsightReport,
    InsightReportMaterial,
    InsightTask,
    InsightTaskStatus,
    InsightUserIntelligencePool,
)
from app.services.agent.insight.data_source_service import insight_data_source_service


async def main() -> None:
    async with async_session() as db:
        summary = {
            "companies": await count_rows(db, InsightCompany, InsightCompany.is_deleted == 0),
            "data_sources": await count_rows(db, InsightDataSource, InsightDataSource.is_deleted == 0),
            "enabled_data_sources": await count_rows(
                db,
                InsightDataSource,
                InsightDataSource.is_deleted == 0,
                InsightDataSource.status == "enabled",
            ),
            "scheduled_data_sources": await count_rows(
                db,
                InsightDataSource,
                InsightDataSource.is_deleted == 0,
                InsightDataSource.status == "enabled",
                InsightDataSource.schedule_enabled == True,  # noqa: E712
            ),
            "due_data_sources": await count_rows(
                db,
                InsightDataSource,
                InsightDataSource.is_deleted == 0,
                InsightDataSource.status == "enabled",
                InsightDataSource.schedule_enabled == True,  # noqa: E712
                InsightDataSource.next_run_time <= func.now(),
            ),
            "candidates": await count_rows(db, InsightIntelligenceCandidate, InsightIntelligenceCandidate.is_deleted == 0),
            "intelligences": await count_rows(db, InsightIntelligence, InsightIntelligence.is_deleted == 0),
            "report_material_pool": await count_rows(
                db,
                InsightUserIntelligencePool,
                InsightUserIntelligencePool.is_deleted == 0,
                InsightUserIntelligencePool.pool_type == "report_material",
                InsightUserIntelligencePool.status == "active",
            ),
            "reports": await count_rows(db, InsightReport, InsightReport.is_deleted == 0),
            "report_materials": await count_rows(db, InsightReportMaterial, InsightReportMaterial.is_deleted == 0),
            "unfinished_tasks": await count_rows(
                db,
                InsightTask,
                InsightTask.is_deleted == 0,
                InsightTask.status.in_([InsightTaskStatus.PENDING, InsightTaskStatus.RUNNING]),
            ),
        }
        checks = {
            "has_companies": summary["companies"] >= 4,
            "has_data_sources": summary["data_sources"] >= 4,
            "has_intelligences": summary["intelligences"] >= 100,
            "has_report_material_pool": summary["report_material_pool"] >= 50,
            "has_reports": summary["reports"] >= 1,
            "has_report_materials": summary["report_materials"] >= 50,
            "no_unfinished_tasks": summary["unfinished_tasks"] == 0,
            "schedule_scan_available": callable(insight_data_source_service.run_due_data_sources),
        }
        print({"summary": summary, "checks": checks, "passed": all(checks.values())})


async def count_rows(db, model, *filters) -> int:
    return (await db.exec(select(func.count()).select_from(model).where(*filters))).one()


if __name__ == "__main__":
    asyncio.run(main())
