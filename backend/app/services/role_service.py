from typing import Optional, List
from sqlmodel import select, func, delete
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.system.sys_role import SysRole, SysUserRole
from app.schemas.role import RoleCreate, RoleUpdate
from app.schemas.page import Page
from app.models.system.sys_user import SysUser


class RoleService:
    @staticmethod
    async def get_by_id(db: AsyncSession, role_id: int) -> Optional[SysRole]:
        return await db.get(SysRole, role_id)

    @staticmethod
    async def get_by_code(db: AsyncSession, code: str) -> Optional[SysRole]:
        query = select(SysRole).where(SysRole.code == code, SysRole.is_deleted == 0)
        result = await db.exec(query)
        return result.first()

    @staticmethod
    async def get_list(
        db: AsyncSession, page: int = 1, size: int = 20, name: Optional[str] = None
    ) -> Page[SysRole]:
        query = select(SysRole).where(SysRole.is_deleted == 0)
        if name:
            query = query.where(SysRole.name.contains(name))

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.exec(count_query)).one()

        # Select
        query = (
            query.order_by(SysRole.order.asc()).offset((page - 1) * size).limit(size)
        )
        result = await db.exec(query)
        items = result.all()

        return Page(total=total, items=items, page=page, size=size)

    @staticmethod
    async def create(db: AsyncSession, obj_in: RoleCreate) -> SysRole:
        db_obj = SysRole.model_validate(obj_in)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(db: AsyncSession, db_obj: SysRole, obj_in: RoleUpdate) -> SysRole:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(db: AsyncSession, db_obj: SysRole) -> None:
        db_obj.is_deleted = 1
        db.add(db_obj)
        await db.commit()

    @staticmethod
    async def assign_to_user(
        db: AsyncSession, user_id: int, role_ids: List[int]
    ) -> None:
        # Remove old links
        await db.exec(delete(SysUserRole).where(SysUserRole.user_id == user_id))
        # Add new links
        for rid in role_ids:
            db.add(SysUserRole(user_id=user_id, role_id=rid))
        await db.commit()

    @staticmethod
    async def get_user_role_ids(db: AsyncSession, user_id: int) -> List[int]:
        query = select(SysUserRole.role_id).where(SysUserRole.user_id == user_id)
        result = await db.exec(query)
        return result.all()

    @staticmethod
    async def assign_users_to_role(
        db: AsyncSession, role_id: int, user_ids: List[int]
    ) -> None:
        # Remove old links for this role
        await db.exec(delete(SysUserRole).where(SysUserRole.role_id == role_id))
        # Add new links
        for uid in user_ids:
            db.add(SysUserRole(user_id=uid, role_id=role_id))
        await db.commit()

    @staticmethod
    async def get_role_user_ids(db: AsyncSession, role_id: int) -> List[int]:
        query = select(SysUserRole.user_id).where(SysUserRole.role_id == role_id)
        result = await db.exec(query)
        return result.all()

    @staticmethod
    async def get_role_users(db: AsyncSession, role_id: int) -> List[SysUser]:

        query = (
            select(SysUser)
            .join(SysUserRole, SysUser.id == SysUserRole.user_id)
            .where(SysUserRole.role_id == role_id, SysUser.is_deleted == 0)
        )
        result = await db.exec(query)
        return result.all()
