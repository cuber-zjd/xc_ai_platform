from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, false, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import InsightVisibilityRule
from app.models.system.sys_company import SysCompany
from app.models.system.sys_dept import SysDept
from app.models.system.sys_role import SysUserRole
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.permission import InsightAccessRuleBulkResponse, InsightAccessRuleBulkUpsert, InsightAccessRuleRead, InsightAccessRuleUpsert


class InsightPermissionService:
    readable_permissions = ("view", "edit", "owner")
    editable_permissions = ("edit", "owner")

    def visibility_filter(
        self,
        model: Any,
        *,
        target_type: str,
        user_id: int,
        is_admin: bool,
        permission: str = "view",
    ):
        if is_admin:
            return True
        permissions = self.editable_permissions if permission == "edit" else self.readable_permissions
        clauses = []
        if hasattr(model, "owner_user_id"):
            clauses.append(model.owner_user_id == user_id)
        if hasattr(model, "visibility_scope"):
            clauses.append(model.visibility_scope == "public")
        clauses.append(
            exists()
            .where(
                InsightVisibilityRule.target_type == target_type,
                InsightVisibilityRule.target_id == model.id,
                InsightVisibilityRule.principal_type == "user",
                InsightVisibilityRule.principal_id == user_id,
                InsightVisibilityRule.permission.in_(permissions),
                InsightVisibilityRule.status == "active",
                InsightVisibilityRule.is_deleted == 0,
            )
            .correlate(model)
        )
        clauses.append(
            exists()
            .where(
                InsightVisibilityRule.target_type == target_type,
                InsightVisibilityRule.target_id == model.id,
                InsightVisibilityRule.principal_type == "all",
                InsightVisibilityRule.permission.in_(permissions),
                InsightVisibilityRule.status == "active",
                InsightVisibilityRule.is_deleted == 0,
            )
            .correlate(model)
        )
        return or_(*clauses)

    async def visibility_filter_for_user(
        self,
        db: AsyncSession,
        model: Any,
        *,
        target_type: str,
        user_id: int | None,
        is_admin: bool,
        permission: str = "view",
    ):
        if is_admin:
            return True
        if not user_id:
            return false()

        role_ids = list(
            (
                await db.exec(
                    select(SysUserRole.role_id).where(
                        SysUserRole.user_id == user_id,
                        SysUserRole.is_deleted == 0,
                    )
                )
            ).all()
        )
        user = (
            await db.exec(
                select(SysUser).where(
                    SysUser.id == user_id,
                    SysUser.is_deleted == 0,
                )
            )
        ).first()
        dept_id = self.parse_int(user.dept_id if user else None)
        sys_company_id = await self._resolve_user_sys_company_id(db, user)
        permissions = self.editable_permissions if permission == "edit" else self.readable_permissions

        clauses = []
        if hasattr(model, "owner_user_id"):
            clauses.append(model.owner_user_id == user_id)
        if hasattr(model, "owner_dept_id") and dept_id is not None:
            clauses.append(model.owner_dept_id == dept_id)
        if permission == "view" and hasattr(model, "visibility_scope"):
            clauses.append(model.visibility_scope == "public")

        principal_conditions = [
            InsightVisibilityRule.principal_type == "all",
            and_(InsightVisibilityRule.principal_type == "user", InsightVisibilityRule.principal_id == user_id),
        ]
        if role_ids:
            principal_conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "role",
                    InsightVisibilityRule.principal_id.in_(role_ids),
                )
            )
        if dept_id is not None:
            principal_conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "dept",
                    InsightVisibilityRule.principal_id == dept_id,
                )
            )
        if sys_company_id is not None:
            principal_conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "sys_company",
                    InsightVisibilityRule.principal_id == sys_company_id,
                )
            )

        now = datetime.now()
        clauses.append(
            exists()
            .where(
                InsightVisibilityRule.target_type == target_type,
                InsightVisibilityRule.target_id == model.id,
                InsightVisibilityRule.permission.in_(permissions),
                InsightVisibilityRule.status == "active",
                InsightVisibilityRule.is_deleted == 0,
                or_(*principal_conditions),
                or_(InsightVisibilityRule.effective_from.is_(None), InsightVisibilityRule.effective_from <= now),
                or_(InsightVisibilityRule.effective_to.is_(None), InsightVisibilityRule.effective_to >= now),
            )
            .correlate(model)
        )
        return or_(*clauses) if clauses else false()

    async def visible_target_ids_for_user(
        self,
        db: AsyncSession,
        *,
        target_type: str,
        user_id: int | None,
        permission: str = "view",
    ) -> list[int]:
        if not user_id:
            return []
        role_ids = list(
            (
                await db.exec(
                    select(SysUserRole.role_id).where(
                        SysUserRole.user_id == user_id,
                        SysUserRole.is_deleted == 0,
                    )
                )
            ).all()
        )
        user = (
            await db.exec(
                select(SysUser).where(
                    SysUser.id == user_id,
                    SysUser.is_deleted == 0,
                )
            )
        ).first()
        dept_id = self.parse_int(user.dept_id if user else None)
        sys_company_id = await self._resolve_user_sys_company_id(db, user)
        permissions = self.editable_permissions if permission == "edit" else self.readable_permissions

        principal_conditions = [
            InsightVisibilityRule.principal_type == "all",
            and_(InsightVisibilityRule.principal_type == "user", InsightVisibilityRule.principal_id == user_id),
        ]
        if role_ids:
            principal_conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "role",
                    InsightVisibilityRule.principal_id.in_(role_ids),
                )
            )
        if dept_id is not None:
            principal_conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "dept",
                    InsightVisibilityRule.principal_id == dept_id,
                )
            )
        if sys_company_id is not None:
            principal_conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "sys_company",
                    InsightVisibilityRule.principal_id == sys_company_id,
                )
            )

        now = datetime.now()
        rows = list(
            (
                await db.exec(
                    select(InsightVisibilityRule.target_id).where(
                        InsightVisibilityRule.target_type == target_type,
                        InsightVisibilityRule.permission.in_(permissions),
                        InsightVisibilityRule.status == "active",
                        InsightVisibilityRule.is_deleted == 0,
                        or_(*principal_conditions),
                        or_(InsightVisibilityRule.effective_from.is_(None), InsightVisibilityRule.effective_from <= now),
                        or_(InsightVisibilityRule.effective_to.is_(None), InsightVisibilityRule.effective_to >= now),
                    )
                )
            ).all()
        )
        return rows

    def parse_int(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(str(value))
        except ValueError:
            return None

    async def resolve_user_sys_company_id(self, db: AsyncSession, user_id: int | None) -> int | None:
        if not user_id:
            return None
        user = (
            await db.exec(
                select(SysUser).where(
                    SysUser.id == user_id,
                    SysUser.is_deleted == 0,
                )
            )
        ).first()
        return await self._resolve_user_sys_company_id(db, user)

    async def _resolve_user_sys_company_id(self, db: AsyncSession, user: SysUser | None) -> int | None:
        if not user or not user.dept_id:
            return None
        dept = (
            await db.exec(
                select(SysDept).where(
                    SysDept.sync_id == str(user.dept_id),
                    SysDept.is_deleted == 0,
                )
            )
        ).first()
        if not dept or not dept.company_id:
            return None
        company = (
            await db.exec(
                select(SysCompany).where(
                    SysCompany.sync_id == str(dept.company_id),
                    SysCompany.is_deleted == 0,
                )
            )
        ).first()
        return company.id if company and company.id is not None else None

    async def grant_rule(
        self,
        db: AsyncSession,
        *,
        target_type: str,
        target_id: int,
        payload: InsightAccessRuleUpsert,
        user_id: int | None,
    ) -> InsightAccessRuleRead:
        row = (
            await db.exec(
                select(InsightVisibilityRule).where(
                    InsightVisibilityRule.target_type == target_type,
                    InsightVisibilityRule.target_id == target_id,
                    InsightVisibilityRule.principal_type == payload.principal_type,
                    InsightVisibilityRule.principal_id == payload.principal_id,
                    InsightVisibilityRule.permission == payload.permission,
                    InsightVisibilityRule.is_deleted == 0,
                )
            )
        ).first()
        if not row:
            row = InsightVisibilityRule(
                target_type=target_type,
                target_id=target_id,
                principal_type=payload.principal_type,
                principal_id=payload.principal_id,
                permission=payload.permission,
                create_by=str(user_id) if user_id else None,
                update_by=str(user_id) if user_id else None,
            )
            db.add(row)
        row.grant_type = payload.grant_type
        row.effective_from = payload.effective_from
        row.effective_to = payload.effective_to
        row.status = "active"
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return self._to_read(row)

    async def grant_rules_bulk(
        self,
        db: AsyncSession,
        *,
        target_type: str,
        payload: InsightAccessRuleBulkUpsert,
        user_id: int | None,
    ) -> InsightAccessRuleBulkResponse:
        rows: list[InsightVisibilityRule] = []
        target_ids = list(dict.fromkeys(payload.target_ids))
        for target_id in target_ids:
            row = (
                await db.exec(
                    select(InsightVisibilityRule).where(
                        InsightVisibilityRule.target_type == target_type,
                        InsightVisibilityRule.target_id == target_id,
                        InsightVisibilityRule.principal_type == payload.principal_type,
                        InsightVisibilityRule.principal_id == payload.principal_id,
                        InsightVisibilityRule.permission == payload.permission,
                        InsightVisibilityRule.is_deleted == 0,
                    )
                )
            ).first()
            if not row:
                row = InsightVisibilityRule(
                    target_type=target_type,
                    target_id=target_id,
                    principal_type=payload.principal_type,
                    principal_id=payload.principal_id,
                    permission=payload.permission,
                    create_by=str(user_id) if user_id else None,
                    update_by=str(user_id) if user_id else None,
                )
                db.add(row)
            row.grant_type = payload.grant_type
            row.effective_from = payload.effective_from
            row.effective_to = payload.effective_to
            row.status = "active"
            row.update_by = str(user_id) if user_id else None
            row.update_time = datetime.now()
            rows.append(row)
        await db.commit()
        for row in rows:
            await db.refresh(row)
        return InsightAccessRuleBulkResponse(
            target_type=target_type,
            target_count=len(target_ids),
            rule_count=len(rows),
            rules=[self._to_read(row) for row in rows],
        )

    async def list_rules(self, db: AsyncSession, *, target_type: str, target_id: int) -> list[InsightAccessRuleRead]:
        rows = list(
            (
                await db.exec(
                    select(InsightVisibilityRule)
                    .where(
                        InsightVisibilityRule.target_type == target_type,
                        InsightVisibilityRule.target_id == target_id,
                        InsightVisibilityRule.is_deleted == 0,
                    )
                    .order_by(InsightVisibilityRule.update_time.desc(), InsightVisibilityRule.id.desc())
                )
            ).all()
        )
        return [self._to_read(row) for row in rows]

    async def revoke_rule(self, db: AsyncSession, *, rule_id: int, user_id: int | None) -> None:
        row = await db.get(InsightVisibilityRule, rule_id)
        if not row or row.is_deleted:
            raise ValueError("权限规则不存在")
        row.is_deleted = 1
        row.status = "revoked"
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()

    def _to_read(self, row: InsightVisibilityRule) -> InsightAccessRuleRead:
        return InsightAccessRuleRead(
            id=row.id or 0,
            create_time=row.create_time,
            update_time=row.update_time,
            target_type=row.target_type,
            target_id=row.target_id,
            principal_type=row.principal_type,
            principal_id=row.principal_id,
            permission=row.permission,
            grant_type=row.grant_type,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            status=row.status,
        )


insight_permission_service = InsightPermissionService()
