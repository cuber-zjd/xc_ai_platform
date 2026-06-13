import asyncio
from pathlib import Path
from uuid import uuid4

from sqlmodel import SQLModel, select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightReport, InsightReportExport
from app.models.system.sys_user import SysUser
from app.services.agent.insight.report_service import insight_report_service


MARK = "insight-report-export-acceptance"


async def main() -> None:
    token = uuid4().hex[:10]
    created: dict[str, list[int]] = {"users": [], "reports": [], "exports": []}
    generated_files: list[Path] = []

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session() as db:
        try:
            owner = SysUser(
                username=f"insight_report_export_owner_{token}",
                full_name=f"Insight 报告导出验收所有者{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            other = SysUser(
                username=f"insight_report_export_other_{token}",
                full_name=f"Insight 报告导出验收无权用户{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(owner)
            db.add(other)
            await db.flush()
            created["users"].extend([owner.id or 0, other.id or 0])

            report = InsightReport(
                report_uid=f"report_export_acceptance_{token}",
                title=f"报告导出验收报告{token}",
                report_type="专题报告",
                content_json={
                    "executive_summary": "这是一份用于验证 HTML 导出、导出记录和权限下载的报告。",
                    "chapters": [
                        {
                            "heading": "一、核心发现",
                            "body": "验收报告应被渲染为可下载 HTML，并保留版本、素材和摘要信息。",
                        },
                        {
                            "heading": "二、交付结论",
                            "body": ["导出记录必须可审计。", "下载前必须复用报告查看权限。"],
                        },
                    ],
                },
                summary="报告导出验收摘要",
                status="draft",
                version_no=2,
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

            export = await insight_report_service.export_report(
                db,
                report.id or 0,
                export_format="html",
                user_id=owner.id or 0,
                is_admin=False,
            )
            created["exports"].append(export.id or 0)
            file_path, download_export = await insight_report_service.get_report_export_file(
                db,
                report.id or 0,
                export.id,
                user_id=owner.id or 0,
                is_admin=False,
            )
            generated_files.append(file_path)
            html = file_path.read_text(encoding="utf-8")
            exports = await insight_report_service.list_report_exports(
                db,
                report.id or 0,
                user_id=owner.id or 0,
                is_admin=False,
            )
            denied_download = False
            try:
                await insight_report_service.get_report_export_file(
                    db,
                    report.id or 0,
                    export.id,
                    user_id=other.id or 0,
                    is_admin=False,
                )
            except ValueError:
                denied_download = True

            denied_export = False
            try:
                await insight_report_service.export_report(
                    db,
                    report.id or 0,
                    export_format="pdf",
                    user_id=owner.id or 0,
                    is_admin=False,
                )
            except ValueError:
                denied_export = True

            checks = {
                "导出记录生成成功": export.status == "success" and export.export_format == "html",
                "导出记录绑定报告版本": export.report_id == report.id and export.report_version_no == report.version_no,
                "导出文件存在": file_path.exists() and file_path.is_file(),
                "导出文件内容包含标题": report.title in html,
                "导出文件内容包含章节": "核心发现" in html and "交付结论" in html,
                "导出文件可通过权限用户定位": download_export.id == export.id,
                "导出列表包含本次记录": any(item.id == export.id for item in exports),
                "无权用户不能下载私有报告导出": denied_download,
                "未接入格式会被明确拒绝": denied_export,
            }
            for name, passed in checks.items():
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(checks.values()):
                failed = [name for name, passed in checks.items() if not passed]
                raise SystemExit(f"Insight 报告导出验收未通过: {'; '.join(failed)}")
            print(
                {
                    "report_id": report.id,
                    "export": export.model_dump(mode="json"),
                    "file": str(file_path),
                    "file_size": file_path.stat().st_size,
                }
            )
        finally:
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
