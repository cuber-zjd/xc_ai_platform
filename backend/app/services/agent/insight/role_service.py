from datetime import datetime

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import InsightRole, InsightRoleMember
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.role import (
    InsightRoleCreate,
    InsightRoleMemberRead,
    InsightRoleMemberUpsert,
    InsightRoleRead,
    InsightRoleUpdate,
)
from app.schemas.page import Page


class InsightRoleService:
    allowed_statuses = {"active", "disabled"}

    async def list_roles(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        status: str | None = None,
    ) -> Page[InsightRoleRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightRole.is_deleted == 0]
        if keyword:
            value = f"%{keyword.strip()}%"
            filters.append(or_(InsightRole.role_name.ilike(value), InsightRole.role_code.ilike(value)))
        if status:
            filters.append(InsightRole.status == status)
        total = (await db.exec(select(func.count()).select_from(InsightRole).where(*filters))).one()
        rows = list(
            (
                await db.exec(
                    select(InsightRole)
                    .where(*filters)
                    .order_by(InsightRole.sort_no.asc(), InsightRole.id.asc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        counts = await self._member_counts(db, [row.id for row in rows if row.id])
        return Page.create(
            items=[self._to_read(row, counts.get(row.id or 0, 0)) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    async def create_role(self, db: AsyncSession, payload: InsightRoleCreate, user_id: int | None) -> InsightRoleRead:
        self._validate(payload.model_dump())
        await self._ensure_code_available(db, payload.role_code)
        row = InsightRole(
            role_code=payload.role_code.strip(),
            role_name=payload.role_name.strip(),
            description=payload.description,
            sort_no=payload.sort_no,
            status=payload.status,
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return self._to_read(row, 0)

    async def update_role(self, db: AsyncSession, role_id: int, payload: InsightRoleUpdate, user_id: int | None) -> InsightRoleRead:
        row = await self._get_role(db, role_id)
        data = payload.model_dump(exclude_unset=True)
        merged = {
            "role_code": data.get("role_code", row.role_code),
            "role_name": data.get("role_name", row.role_name),
            "status": data.get("status", row.status),
        }
        self._validate(merged)
        if "role_code" in data and data["role_code"] and data["role_code"].strip() != row.role_code:
            await self._ensure_code_available(db, data["role_code"].strip(), exclude_id=role_id)
        for field, value in data.items():
            if isinstance(value, str) and field in {"role_code", "role_name"}:
                value = value.strip()
            setattr(row, field, value)
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        counts = await self._member_counts(db, [role_id])
        return self._to_read(row, counts.get(role_id, 0))

    async def delete_role(self, db: AsyncSession, role_id: int, user_id: int | None) -> None:
        row = await self._get_role(db, role_id)
        row.is_deleted = 1
        row.status = "disabled"
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        members = list(
            (
                await db.exec(
                    select(InsightRoleMember).where(
                        InsightRoleMember.role_id == role_id,
                        InsightRoleMember.is_deleted == 0,
                    )
                )
            ).all()
        )
        for member in members:
            member.is_deleted = 1
            member.status = "disabled"
            member.update_by = str(user_id) if user_id else None
            member.update_time = datetime.now()
        await db.commit()

    async def list_members(self, db: AsyncSession, role_id: int) -> list[InsightRoleMemberRead]:
        await self._get_role(db, role_id)
        rows = list(
            (
                await db.exec(
                    select(InsightRoleMember, SysUser)
                    .join(SysUser, SysUser.id == InsightRoleMember.user_id)
                    .where(
                        InsightRoleMember.role_id == role_id,
                        InsightRoleMember.is_deleted == 0,
                        SysUser.is_deleted == 0,
                    )
                    .order_by(InsightRoleMember.id.asc())
                )
            ).all()
        )
        return [self._member_to_read(member, user) for member, user in rows]

    async def add_members(
        self,
        db: AsyncSession,
        role_id: int,
        payload: InsightRoleMemberUpsert,
        user_id: int | None,
    ) -> list[InsightRoleMemberRead]:
        await self._get_role(db, role_id)
        user_ids = list(dict.fromkeys([int(item) for item in payload.user_ids if int(item) > 0]))
        if not user_ids:
            return await self.list_members(db, role_id)
        existing = {
            row.user_id: row
            for row in (
                await db.exec(
                    select(InsightRoleMember).where(
                        InsightRoleMember.role_id == role_id,
                        InsightRoleMember.user_id.in_(user_ids),
                    )
                )
            ).all()
        }
        for target_user_id in user_ids:
            row = existing.get(target_user_id)
            if not row:
                row = InsightRoleMember(
                    role_id=role_id,
                    user_id=target_user_id,
                    create_by=str(user_id) if user_id else None,
                    update_by=str(user_id) if user_id else None,
                )
                db.add(row)
            row.status = "active"
            row.is_deleted = 0
            row.update_by = str(user_id) if user_id else None
            row.update_time = datetime.now()
        await db.commit()
        return await self.list_members(db, role_id)

    async def remove_member(self, db: AsyncSession, role_id: int, member_id: int, user_id: int | None) -> None:
        row = await db.get(InsightRoleMember, member_id)
        if not row or row.role_id != role_id or row.is_deleted:
            raise ValueError("角色成员不存在")
        row.is_deleted = 1
        row.status = "disabled"
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()

    async def seed_defaults(self, db: AsyncSession, user_id: int | None = None) -> None:
        defaults = [
            ("insight_full_access", "全量情报查看组", "最高级别数据角色；成员可查看市场洞察内全部情报、资产、报告素材、企业和监测配置，但不自动获得编辑权限", 0),
            ("sales_focus", "销售关注组", "关注客户动态、销售机会、竞品动作和风险线索", 10),
            ("marketing_focus", "市场关注组", "关注行业趋势、客户需求、品牌与舆情变化", 20),
            ("rd_focus", "研发关注组", "关注新品、技术、专利、配方和原料应用变化", 30),
            ("management_view", "管理查看组", "用于管理层查看跨企业、跨主题的重点情报和报告", 40),
        ]
        for code, name, description, sort_no in defaults:
            existing = (
                await db.exec(
                    select(InsightRole).where(
                        InsightRole.role_code == code,
                        InsightRole.is_deleted == 0,
                    )
                )
            ).first()
            if existing:
                continue
            db.add(
                InsightRole(
                    role_code=code,
                    role_name=name,
                    description=description,
                    sort_no=sort_no,
                    create_by=str(user_id) if user_id else None,
                    update_by=str(user_id) if user_id else None,
                )
            )
        await db.commit()

    async def _get_role(self, db: AsyncSession, role_id: int) -> InsightRole:
        row = (
            await db.exec(
                select(InsightRole).where(
                    InsightRole.id == role_id,
                    InsightRole.is_deleted == 0,
                )
            )
        ).first()
        if not row:
            raise ValueError("市场洞察角色不存在")
        return row

    async def _ensure_code_available(self, db: AsyncSession, role_code: str, exclude_id: int | None = None) -> None:
        filters = [InsightRole.role_code == role_code.strip(), InsightRole.is_deleted == 0]
        if exclude_id:
            filters.append(InsightRole.id != exclude_id)
        existing = (await db.exec(select(InsightRole).where(*filters))).first()
        if existing:
            raise ValueError("角色编码已存在")

    async def _member_counts(self, db: AsyncSession, role_ids: list[int]) -> dict[int, int]:
        if not role_ids:
            return {}
        rows = list(
            (
                await db.exec(
                    select(InsightRoleMember.role_id, func.count())
                    .where(
                        InsightRoleMember.role_id.in_(role_ids),
                        InsightRoleMember.is_deleted == 0,
                        InsightRoleMember.status == "active",
                    )
                    .group_by(InsightRoleMember.role_id)
                )
            ).all()
        )
        return {role_id: count for role_id, count in rows}

    def _validate(self, data: dict) -> None:
        if not str(data.get("role_code") or "").strip():
            raise ValueError("角色编码不能为空")
        if not str(data.get("role_name") or "").strip():
            raise ValueError("角色名称不能为空")
        status = str(data.get("status") or "active")
        if status not in self.allowed_statuses:
            raise ValueError(f"角色状态不支持：{status}")

    def _to_read(self, row: InsightRole, member_count: int) -> InsightRoleRead:
        return InsightRoleRead(
            id=row.id or 0,
            create_time=row.create_time,
            update_time=row.update_time,
            create_by=row.create_by,
            update_by=row.update_by,
            comment=row.comment,
            is_deleted=row.is_deleted,
            role_code=row.role_code,
            role_name=row.role_name,
            description=row.description,
            sort_no=row.sort_no,
            status=row.status,
            member_count=member_count,
        )

    def _member_to_read(self, row: InsightRoleMember, user: SysUser) -> InsightRoleMemberRead:
        return InsightRoleMemberRead(
            id=row.id or 0,
            create_time=row.create_time,
            update_time=row.update_time,
            create_by=row.create_by,
            update_by=row.update_by,
            comment=row.comment,
            is_deleted=row.is_deleted,
            role_id=row.role_id,
            user_id=row.user_id,
            user_name=user.full_name or user.username,
            username=user.username,
            employee_id=user.employee_id,
            dept_id=str(user.dept_id) if user.dept_id is not None else None,
            job_title=user.job_title,
            status=row.status,
        )


insight_role_service = InsightRoleService()
