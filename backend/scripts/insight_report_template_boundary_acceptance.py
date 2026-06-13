import asyncio
from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import InsightReport, InsightReportTemplate
from app.models.system.sys_user import SysUser
from app.services.agent.insight.report_service import insight_report_service


MARK = "insight-report-template-boundary-acceptance"


async def main() -> None:
    token = uuid4().hex[:10]
    created: dict[str, list[int]] = {"users": [], "reports": [], "templates": []}

    async with async_session() as db:
        try:
            user = SysUser(
                username=f"insight_template_boundary_{token}",
                full_name=f"Insight 套版边界验收{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(user)
            await db.flush()
            created["users"].append(user.id or 0)

            upload_result = await insight_report_service.create_template_from_upload(
                db,
                file_name=f"套版边界验收{token}.docx",
                file_bytes=build_docx_bytes("套版边界验收标题", "这是用于验证模板解析边界的正文。"),
                template_name=None,
                report_type="专题报告",
                description=None,
                user_id=user.id or 0,
            )
            template = upload_result.template
            if template.id:
                created["templates"].append(template.id)

            report = InsightReport(
                report_uid=f"template_boundary_report_{token}",
                title=f"套版边界验收报告{token}",
                report_type="专题报告",
                content_json={"executive_summary": "用于验证 DOCX 套版导出边界。", "chapters": []},
                summary="套版边界验收摘要",
                owner_user_id=user.id,
                visibility_scope="private",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(report)
            await db.commit()
            await db.refresh(report)
            created["reports"].append(report.id or 0)

            rejected_docx_export = False
            rejected_message = ""
            try:
                await insight_report_service.export_report(
                    db,
                    report.id or 0,
                    export_format="docx",
                    user_id=user.id or 0,
                    is_admin=False,
                )
            except ValueError as exc:
                rejected_docx_export = True
                rejected_message = str(exc)

            boundary = template.structure_json.get("export_boundary") if isinstance(template.structure_json, dict) else None
            checks = {
                "上传模板保留源文件类型": template.source_file_type == "docx",
                "上传模板记录源文件名": bool(template.source_file_name and template.source_file_name.endswith(".docx")),
                "上传模板只用于结构解析": isinstance(boundary, dict) and boundary.get("parse_supported") is True,
                "上传模板明确套版未接入": isinstance(boundary, dict) and boundary.get("templated_export_supported") is False,
                "上传模板不声明 DOCX 可导出": "docx" not in (template.export_formats or []),
                "报告 DOCX 导出被拒绝": rejected_docx_export,
                "拒绝信息说明当前仅支持 HTML": "HTML" in rejected_message and "DOCX" in rejected_message,
            }
            for name, passed in checks.items():
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(checks.values()):
                failed = [name for name, passed in checks.items() if not passed]
                raise SystemExit(f"Insight DOCX/XLSX 套版边界验收未通过: {'; '.join(failed)}")
            print(
                {
                    "template": template.model_dump(mode="json"),
                    "export_boundary": boundary,
                    "rejected_message": rejected_message,
                }
            )
        finally:
            await cleanup(db, created)


def build_docx_bytes(title: str, body: str) -> bytes:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{title}</w:t></w:r></w:p>
    <w:p><w:r><w:t>{body}</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>"""
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


async def cleanup(db, created: dict[str, list[int]]) -> None:
    model_map = {
        "templates": InsightReportTemplate,
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
