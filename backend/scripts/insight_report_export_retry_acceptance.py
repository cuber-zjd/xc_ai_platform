import asyncio
from pathlib import Path
from types import MethodType
from uuid import uuid4

from sqlmodel import SQLModel, select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightReport, InsightReportExport
from app.models.system.sys_user import SysUser
from app.services.agent.insight.report_service import InsightReportService, insight_report_service


MARK = "insight-report-export-retry-acceptance"


async def main() -> None:
    token = uuid4().hex[:10]
    created: dict[str, list[int]] = {"users": [], "reports": [], "exports": []}
    generated_files: list[Path] = []

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as db:
        original_renderer = insight_report_service._render_report_html
        try:
            owner = SysUser(
                username=f"insight_export_retry_owner_{token}",
                full_name=f"Insight 导出重试验收用户{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(owner)
            await db.flush()
            created["users"].append(owner.id or 0)

            report = InsightReport(
                report_uid=f"report_export_retry_acceptance_{token}",
                title=f"报告导出失败重试验收{token}",
                report_type="专题报告",
                content_json={
                    "executive_summary": "用于验证导出失败记录和重试成功。",
                    "chapters": [{"heading": "导出重试", "body": "第一次失败后应保留错误，第二次可重新导出成功。"}],
                },
                summary="导出失败重试验收摘要",
                status="draft",
                version_no=3,
                material_count=0,
                owner_user_id=owner.id,
                visibility_scope="private",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(report)
            await db.commit()
            await db.refresh(report)
            created["reports"].append(report.id or 0)

            def fail_renderer(self: InsightReportService, detail):  # noqa: ANN001
                raise RuntimeError("模拟 HTML 渲染失败")

            insight_report_service._render_report_html = MethodType(fail_renderer, insight_report_service)
            failed_export = await insight_report_service.export_report(
                db,
                report.id or 0,
                export_format="html",
                user_id=owner.id or 0,
                is_admin=False,
            )
            created["exports"].append(failed_export.id)

            download_failed_blocked = False
            try:
                await insight_report_service.get_report_export_file(
                    db,
                    report.id or 0,
                    failed_export.id,
                    user_id=owner.id or 0,
                    is_admin=False,
                )
            except ValueError:
                download_failed_blocked = True

            insight_report_service._render_report_html = original_renderer
            success_export = await insight_report_service.export_report(
                db,
                report.id or 0,
                export_format="html",
                user_id=owner.id or 0,
                is_admin=False,
            )
            created["exports"].append(success_export.id)
            file_path, download_export = await insight_report_service.get_report_export_file(
                db,
                report.id or 0,
                success_export.id,
                user_id=owner.id or 0,
                is_admin=False,
            )
            generated_files.append(file_path)
            exports = await insight_report_service.list_report_exports(
                db,
                report.id or 0,
                user_id=owner.id or 0,
                is_admin=False,
            )

            checks = {
                "失败导出记录保留": failed_export.status == "failed" and failed_export.error_message and "模拟 HTML 渲染失败" in failed_export.error_message,
                "失败导出没有文件": not failed_export.file_name and failed_export.file_size is None,
                "失败记录不能下载": download_failed_blocked,
                "重试生成新记录": success_export.id != failed_export.id and success_export.status == "success",
                "重试文件可下载": download_export.id == success_export.id and file_path.exists() and file_path.is_file(),
                "导出列表同时包含失败和成功": {failed_export.id, success_export.id}.issubset({item.id for item in exports}),
                "失败历史仍可审计": any(item.id == failed_export.id and item.status == "failed" for item in exports),
            }
            for name, passed in checks.items():
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(checks.values()):
                failed = [name for name, passed in checks.items() if not passed]
                raise SystemExit(f"Insight 报告导出失败重试验收未通过: {'; '.join(failed)}")
            print(
                {
                    "report_id": report.id,
                    "failed_export": failed_export.model_dump(mode="json"),
                    "success_export": success_export.model_dump(mode="json"),
                    "file": str(file_path),
                }
            )
        finally:
            insight_report_service._render_report_html = original_renderer
            await cleanup(db, created)
            for file_path in generated_files:
                if file_path.exists():
                    file_path.unlink()


async def cleanup(db, created: dict[str, list[int]]) -> None:
    model_map = {
        "exports": InsightReportExport,
        "reports": InsightReport,
        "users": SysUser,
    }
    for key, model in model_map.items():
        ids = [item_id for item_id in created[key] if item_id]
        if not ids:
            continue
        rows = list((await db.exec(select(model).where(model.id.in_(ids)))).all())
        for row in rows:
            row.is_deleted = 1
            row.update_by = f"{MARK}-cleanup"
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
