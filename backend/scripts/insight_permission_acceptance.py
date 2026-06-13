import asyncio
from uuid import uuid4

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import InsightCompany, InsightDataSource, InsightReport, InsightVisibilityRule
from app.models.system.sys_role import SysRole, SysUserRole
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.data_source import InsightDataSourceExecuteRequest
from app.schemas.agent.insight.report import InsightReportUpdateRequest
from app.services.agent.insight.company_service import insight_company_service
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.report_service import insight_report_service


async def main() -> None:
    token = uuid4().hex[:10]
    dept_id = 880000 + int(token[:4], 16) % 10000
    created: dict[str, list[int]] = {
        "users": [],
        "roles": [],
        "user_roles": [],
        "companies": [],
        "data_sources": [],
        "reports": [],
        "rules": [],
    }
    async with async_session() as db:
        try:
            await cleanup_stale_acceptance_rows(db)
            owner = await create_user(db, token, "owner", dept_id=None, created=created)
            role_user = await create_user(db, token, "role", dept_id=None, created=created)
            dept_user = await create_user(db, token, "dept", dept_id=dept_id, created=created)
            other_user = await create_user(db, token, "other", dept_id=None, created=created)
            role = SysRole(name=f"Insight验收角色{token}", code=f"insight_accept_{token}", create_by="acceptance")
            db.add(role)
            await db.commit()
            await db.refresh(role)
            created["roles"].append(role.id or 0)
            user_role = SysUserRole(user_id=role_user.id or 0, role_id=role.id or 0, create_by="acceptance")
            db.add(user_role)
            await db.commit()
            await db.refresh(user_role)
            created["user_roles"].append(user_role.id or 0)

            company = InsightCompany(
                company_code=f"insight_accept_company_{token}",
                name=f"Insight权限验收企业{token}",
                owner_user_id=owner.id,
                create_by="acceptance",
                update_by="acceptance",
            )
            db.add(company)
            await db.commit()
            await db.refresh(company)
            created["companies"].append(company.id or 0)

            data_source = InsightDataSource(
                source_code=f"insight_accept_source_{token}",
                source_name=f"Insight权限验收数据源{token}",
                source_type="web_page",
                base_url="https://example.com",
                company_id=company.id,
                owner_user_id=owner.id,
                visibility_scope="private",
                status="enabled",
                create_by="acceptance",
                update_by="acceptance",
            )
            db.add(data_source)
            report = InsightReport(
                report_uid=f"insight_accept_report_{token}",
                title=f"Insight权限验收报告{token}",
                content_json={"executive_summary": "权限验收临时报告"},
                summary="权限验收临时报告",
                owner_user_id=owner.id,
                visibility_scope="private",
                create_by="acceptance",
                update_by="acceptance",
            )
            db.add(report)
            await db.commit()
            await db.refresh(data_source)
            await db.refresh(report)
            created["data_sources"].append(data_source.id or 0)
            created["reports"].append(report.id or 0)

            checks: list[tuple[str, bool]] = []
            owner_companies = await insight_company_service.list_companies(
                db,
                page=1,
                size=20,
                keyword=token,
                industry=None,
                monitor_level=None,
                status=None,
                user_id=owner.id or 0,
                is_admin=False,
            )
            checks.append(("企业 owner 可见", contains_id(owner_companies.items, company.id)))
            other_companies = await insight_company_service.list_companies(
                db,
                page=1,
                size=20,
                keyword=token,
                industry=None,
                monitor_level=None,
                status=None,
                user_id=other_user.id or 0,
                is_admin=False,
            )
            checks.append(("企业无权用户不可见", not contains_id(other_companies.items, company.id)))

            await grant_rule(db, "company", company.id or 0, "role", role.id, "view", created)
            role_companies = await insight_company_service.list_companies(
                db,
                page=1,
                size=20,
                keyword=token,
                industry=None,
                monitor_level=None,
                status=None,
                user_id=role_user.id or 0,
                is_admin=False,
            )
            checks.append(("企业角色授权可见", contains_id(role_companies.items, company.id)))
            await grant_rule(db, "company", company.id or 0, "dept", dept_id, "view", created)
            dept_detail = await insight_company_service.get_company_detail(
                db,
                company.id or 0,
                user_id=dept_user.id or 0,
                is_admin=False,
            )
            checks.append(("企业部门授权详情可见", dept_detail.id == company.id))
            try:
                await insight_company_service.get_company_detail(
                    db,
                    company.id or 0,
                    user_id=other_user.id or 0,
                    is_admin=False,
                )
                checks.append(("企业无权详情被阻断", False))
            except ValueError:
                checks.append(("企业无权详情被阻断", True))

            await grant_rule(db, "data_source", data_source.id or 0, "role", role.id, "view", created)
            role_sources = await insight_data_source_service.list_data_sources(
                db,
                page=1,
                size=20,
                keyword=token,
                source_type=None,
                status=None,
                user_id=role_user.id or 0,
                is_admin=False,
            )
            checks.append(("数据源角色 view 可见", contains_id(role_sources.items, data_source.id)))
            try:
                await insight_data_source_service.execute_data_source(
                    db,
                    data_source.id or 0,
                    InsightDataSourceExecuteRequest(),
                    role_user.id,
                    is_admin=False,
                )
                checks.append(("数据源 view 不能执行", False))
            except ValueError:
                checks.append(("数据源 view 不能执行", True))
            await grant_rule(db, "data_source", data_source.id or 0, "dept", dept_id, "edit", created)
            editable_source = await insight_data_source_service.get_data_source(
                db,
                data_source.id or 0,
                user_id=dept_user.id or 0,
                is_admin=False,
            )
            checks.append(("数据源部门 edit 可读", editable_source.id == data_source.id))

            await grant_rule(db, "report", report.id or 0, "role", role.id, "view", created)
            role_reports = await insight_report_service.list_reports(
                db,
                page=1,
                size=20,
                keyword=token,
                report_type=None,
                status=None,
                user_id=role_user.id or 0,
                is_admin=False,
            )
            checks.append(("报告角色 view 可见", contains_id(role_reports.items, report.id)))
            try:
                await insight_report_service.update_report(
                    db,
                    report.id or 0,
                    payload=InsightReportUpdateRequest(summary="不应成功"),
                    user_id=role_user.id or 0,
                    is_admin=False,
                )
                checks.append(("报告 view 不能编辑", False))
            except Exception:
                checks.append(("报告 view 不能编辑", True))
            await grant_rule(db, "report", report.id or 0, "dept", dept_id, "edit", created)
            report_detail = await insight_report_service.get_report_detail(
                db,
                report.id or 0,
                user_id=dept_user.id or 0,
                is_admin=False,
            )
            checks.append(("报告部门 edit 可读", report_detail.id == report.id))

            failed = [name for name, ok in checks if not ok]
            for name, ok in checks:
                print(f"[{'PASS' if ok else 'FAIL'}] {name}")
            if failed:
                raise SystemExit(f"Insight 权限验收未通过: {'; '.join(failed)}")
        finally:
            await cleanup(db, created)


async def create_user(db, token: str, suffix: str, *, dept_id: int | None, created: dict[str, list[int]]) -> SysUser:
    user = SysUser(
        username=f"insight_accept_{suffix}_{token}",
        full_name=f"Insight权限验收{suffix}{token}",
        dept_id=str(dept_id) if dept_id is not None else None,
        hashed_password="acceptance-only",
        create_by="acceptance",
        update_by="acceptance",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    created["users"].append(user.id or 0)
    return user


async def grant_rule(
    db,
    target_type: str,
    target_id: int,
    principal_type: str,
    principal_id: int | None,
    permission: str,
    created: dict[str, list[int]],
) -> None:
    rule = InsightVisibilityRule(
        target_type=target_type,
        target_id=target_id,
        principal_type=principal_type,
        principal_id=principal_id,
        permission=permission,
        create_by="acceptance",
        update_by="acceptance",
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    created["rules"].append(rule.id or 0)


def contains_id(items, expected_id: int | None) -> bool:
    return any(item.id == expected_id for item in items)


async def cleanup(db, created: dict[str, list[int]]) -> None:
    model_map = {
        "rules": InsightVisibilityRule,
        "reports": InsightReport,
        "data_sources": InsightDataSource,
        "companies": InsightCompany,
        "user_roles": SysUserRole,
        "roles": SysRole,
        "users": SysUser,
    }
    for key, model in model_map.items():
        ids = [item_id for item_id in created[key] if item_id]
        if not ids:
            continue
        rows = list((await db.exec(select(model).where(model.id.in_(ids)))).all())
        for row in rows:
            row.is_deleted = 1
            row.update_by = "acceptance-cleanup"
        await db.commit()


async def cleanup_stale_acceptance_rows(db) -> None:
    for model in (InsightVisibilityRule, InsightReport, InsightDataSource, InsightCompany, SysUserRole, SysRole, SysUser):
        rows = list(
            (
                await db.exec(
                    select(model).where(
                        model.create_by == "acceptance",
                        model.is_deleted == 0,
                    )
                )
            ).all()
        )
        for row in rows:
            row.is_deleted = 1
            row.update_by = "acceptance-cleanup"
        if rows:
            await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
