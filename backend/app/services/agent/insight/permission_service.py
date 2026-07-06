from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, false, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import InsightIntelligence, InsightRole, InsightRoleMember, InsightVisibilityRule
from app.models.system.sys_company import SysCompany
from app.models.system.sys_dept import SysDept
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.permission import InsightAccessRuleBulkResponse, InsightAccessRuleBulkUpsert, InsightAccessRuleRead, InsightAccessRuleUpsert


class InsightPermissionService:
    readable_permissions = ("view", "edit", "owner")
    editable_permissions = ("edit", "owner")
    full_visibility_role_codes = ("insight_full_access",)

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
        if permission == "view" and await self.has_full_visibility_role(db, user_id):
            return True

        role_ids, dept_id, sys_company_id = await self._principal_context(db, user_id)
        permissions = self.editable_permissions if permission == "edit" else self.readable_permissions

        clauses = []
        if hasattr(model, "owner_user_id"):
            clauses.append(model.owner_user_id == user_id)
        if hasattr(model, "owner_dept_id") and dept_id is not None:
            clauses.append(model.owner_dept_id == dept_id)

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

    async def inherited_intelligence_filter_for_user(
        self,
        db: AsyncSession,
        intelligence_model: Any,
        *,
        user_id: int | None,
        is_admin: bool,
        permission: str = "view",
    ):
        """正式情报继承企业档案和监测配置授权，减少逐条授权成本。"""
        if is_admin:
            return True
        if not user_id:
            return false()
        if permission == "view" and await self.has_full_visibility_role(db, user_id):
            return True

        role_ids, dept_id, sys_company_id = await self._principal_context(db, user_id)
        permissions = self.editable_permissions if permission == "edit" else self.readable_permissions
        principal_conditions = self._principal_conditions(
            user_id=user_id,
            role_ids=role_ids,
            dept_id=dept_id,
            sys_company_id=sys_company_id,
        )
        now = datetime.now()
        base_rule_filters = [
            InsightVisibilityRule.permission.in_(permissions),
            InsightVisibilityRule.status == "active",
            InsightVisibilityRule.is_deleted == 0,
            or_(*principal_conditions),
            or_(InsightVisibilityRule.effective_from.is_(None), InsightVisibilityRule.effective_from <= now),
            or_(InsightVisibilityRule.effective_to.is_(None), InsightVisibilityRule.effective_to >= now),
        ]
        clauses = []
        if hasattr(intelligence_model, "company_id"):
            clauses.append(
                exists()
                .where(
                    InsightVisibilityRule.target_type == "company",
                    InsightVisibilityRule.target_id == intelligence_model.company_id,
                    *base_rule_filters,
                )
                .correlate(intelligence_model)
            )
        if hasattr(intelligence_model, "monitor_config_id"):
            clauses.append(
                exists()
                .where(
                    InsightVisibilityRule.target_type == "monitor_config",
                    InsightVisibilityRule.target_id == intelligence_model.monitor_config_id,
                    *base_rule_filters,
                )
                .correlate(intelligence_model)
            )
        return or_(*clauses) if clauses else false()

    async def inherited_asset_filter_for_user(
        self,
        db: AsyncSession,
        asset_model: Any,
        *,
        user_id: int | None,
        is_admin: bool,
        permission: str = "view",
    ):
        """情报资产继承企业档案、正式情报和监测配置授权。"""
        if is_admin:
            return True
        if not user_id:
            return false()
        if permission == "view" and await self.has_full_visibility_role(db, user_id):
            return True

        role_ids, dept_id, sys_company_id = await self._principal_context(db, user_id)
        permissions = self.editable_permissions if permission == "edit" else self.readable_permissions
        principal_conditions = self._principal_conditions(
            user_id=user_id,
            role_ids=role_ids,
            dept_id=dept_id,
            sys_company_id=sys_company_id,
        )
        now = datetime.now()
        base_rule_filters = [
            InsightVisibilityRule.permission.in_(permissions),
            InsightVisibilityRule.status == "active",
            InsightVisibilityRule.is_deleted == 0,
            or_(*principal_conditions),
            or_(InsightVisibilityRule.effective_from.is_(None), InsightVisibilityRule.effective_from <= now),
            or_(InsightVisibilityRule.effective_to.is_(None), InsightVisibilityRule.effective_to >= now),
        ]
        clauses = []
        if hasattr(asset_model, "company_id"):
            clauses.append(
                exists()
                .where(
                    InsightVisibilityRule.target_type == "company",
                    InsightVisibilityRule.target_id == asset_model.company_id,
                    *base_rule_filters,
                )
                .correlate(asset_model)
            )
        if hasattr(asset_model, "intelligence_id"):
            clauses.append(
                exists()
                .where(
                    InsightVisibilityRule.target_type == "intelligence",
                    InsightVisibilityRule.target_id == asset_model.intelligence_id,
                    *base_rule_filters,
                )
                .correlate(asset_model)
            )
            clauses.append(
                exists()
                .where(
                    InsightIntelligence.id == asset_model.intelligence_id,
                    InsightIntelligence.is_deleted == 0,
                    InsightVisibilityRule.target_type == "monitor_config",
                    InsightVisibilityRule.target_id == InsightIntelligence.monitor_config_id,
                    *base_rule_filters,
                )
                .correlate(asset_model)
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
        if permission == "view" and await self.has_full_visibility_role(db, user_id):
            if target_type == "intelligence":
                return list(
                    (
                        await db.exec(
                            select(InsightIntelligence.id).where(
                                InsightIntelligence.is_deleted == 0,
                                InsightIntelligence.status == "active",
                            )
                        )
                    ).all()
                )
        role_ids, dept_id, sys_company_id = await self._principal_context(db, user_id)
        permissions = self.editable_permissions if permission == "edit" else self.readable_permissions

        principal_conditions = self._principal_conditions(
            user_id=user_id,
            role_ids=role_ids,
            dept_id=dept_id,
            sys_company_id=sys_company_id,
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

    async def _principal_context(self, db: AsyncSession, user_id: int) -> tuple[list[int], int | None, int | None]:
        role_ids = list(
            (
                await db.exec(
                    select(InsightRoleMember.role_id)
                    .join(InsightRole, InsightRole.id == InsightRoleMember.role_id)
                    .where(
                        InsightRoleMember.user_id == user_id,
                        InsightRoleMember.is_deleted == 0,
                        InsightRoleMember.status == "active",
                        InsightRole.is_deleted == 0,
                        InsightRole.status == "active",
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
        return role_ids, dept_id, sys_company_id

    async def has_full_visibility_role(self, db: AsyncSession, user_id: int | None) -> bool:
        if not user_id:
            return False
        row = (
            await db.exec(
                select(InsightRoleMember.id)
                .join(InsightRole, InsightRole.id == InsightRoleMember.role_id)
                .where(
                    InsightRoleMember.user_id == user_id,
                    InsightRoleMember.is_deleted == 0,
                    InsightRoleMember.status == "active",
                    InsightRole.role_code.in_(self.full_visibility_role_codes),
                    InsightRole.is_deleted == 0,
                    InsightRole.status == "active",
                )
                .limit(1)
            )
        ).first()
        return row is not None

    def _principal_conditions(
        self,
        *,
        user_id: int,
        role_ids: list[int],
        dept_id: int | None,
        sys_company_id: int | None,
    ) -> list[Any]:
        conditions: list[Any] = [
            InsightVisibilityRule.principal_type == "all",
            and_(InsightVisibilityRule.principal_type == "user", InsightVisibilityRule.principal_id == user_id),
        ]
        if role_ids:
            conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "role",
                    InsightVisibilityRule.principal_id.in_(role_ids),
                )
            )
        if dept_id is not None:
            conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "dept",
                    InsightVisibilityRule.principal_id == dept_id,
                )
            )
        if sys_company_id is not None:
            conditions.append(
                and_(
                    InsightVisibilityRule.principal_type == "sys_company",
                    InsightVisibilityRule.principal_id == sys_company_id,
                )
            )
        return conditions

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
        return await self._to_read(db, row)

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
            rules=[await self._to_read(db, row) for row in rows],
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
        return [await self._to_read(db, row) for row in rows]

    async def revoke_rule(self, db: AsyncSession, *, rule_id: int, user_id: int | None) -> None:
        row = await db.get(InsightVisibilityRule, rule_id)
        if not row or row.is_deleted:
            raise ValueError("权限规则不存在")
        row.is_deleted = 1
        row.status = "revoked"
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()

    async def _to_read(self, db: AsyncSession, row: InsightVisibilityRule) -> InsightAccessRuleRead:
        principal_name, principal_code = await self._principal_display(db, row)
        return InsightAccessRuleRead(
            id=row.id or 0,
            create_time=row.create_time,
            update_time=row.update_time,
            target_type=row.target_type,
            target_id=row.target_id,
            principal_type=row.principal_type,
            principal_id=row.principal_id,
            principal_name=principal_name,
            principal_code=principal_code,
            permission=row.permission,
            grant_type=row.grant_type,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            status=row.status,
        )

    async def _principal_display(self, db: AsyncSession, row: InsightVisibilityRule) -> tuple[str | None, str | None]:
        if row.principal_type == "all":
            return "全员", None
        if row.principal_id is None:
            return None, None
        if row.principal_type == "user":
            user = await db.get(SysUser, row.principal_id)
            if user:
                return user.full_name or user.username, user.employee_id or user.username
        if row.principal_type == "role":
            role = await db.get(InsightRole, row.principal_id)
            if role:
                return role.role_name, role.role_code
        if row.principal_type == "dept":
            dept = (
                await db.exec(
                    select(SysDept).where(
                        SysDept.is_deleted == 0,
                        or_(SysDept.id == row.principal_id, SysDept.sync_id == str(row.principal_id)),
                    )
                )
            ).first()
            if dept:
                return dept.name, dept.code or dept.sync_id
        if row.principal_type == "sys_company":
            company = await db.get(SysCompany, row.principal_id)
            if company:
                return company.name, company.code or company.sync_id
        return None, None


insight_permission_service = InsightPermissionService()
