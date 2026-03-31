from typing import Optional, List
from sqlmodel import select, func, cast, String
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.system.sys_user import SysUser
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash
from app.schemas.page import Page

class UserService:
    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> Optional[SysUser]:
        query = select(SysUser).where(SysUser.username == username, SysUser.status == 1)
        result = await db.exec(query)
        return result.first()

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: str) -> Optional[SysUser]:
        return await db.get(SysUser, user_id)

    @staticmethod
    async def get_list(
        db: AsyncSession, page: int = 1, size: int = 20, dept_id: int | None = None, **filters
    ) -> Page[SysUser]:
        # Base query with status=1 filter
        base_query = select(SysUser).where(SysUser.status == 1, SysUser.is_deleted == 0)
        
        if dept_id:
            base_query = base_query.where(SysUser.dept_id == cast(str(dept_id), String))
        
        # Count
        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await db.exec(count_query)).one()
        
        # Select with pagination
        query = base_query.offset((page - 1) * size).limit(size)
        result = await db.exec(query)
        items = list(result.all())
        
        return Page(total=total, items=items, page=page, size=size)

    @staticmethod
    async def create(db: AsyncSession, obj_in: UserCreate) -> SysUser:
        db_obj = SysUser(
            username=obj_in.username,
            hashed_password=get_password_hash(obj_in.password),
            full_name=obj_in.full_name,
            email=obj_in.email,
            is_superuser=obj_in.is_superuser,
            dept_id=obj_in.dept_id,
            status=obj_in.status
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(
        db: AsyncSession, db_obj: SysUser, obj_in: UserUpdate
    ) -> SysUser:
        update_data = obj_in.model_dump(exclude_unset=True)
        
        if "password" in update_data and update_data["password"]:
            hashed_password = get_password_hash(update_data["password"])
            del update_data["password"]
            db_obj.hashed_password = hashed_password
            
        for field, value in update_data.items():
            setattr(db_obj, field, value)
            
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(db: AsyncSession, db_obj: SysUser) -> None:
        # Soft delete usually preferred, assuming is_deleted exists on BaseDBModel
        # But let's check SysUserBase. 
        # BaseDBModel usually has is_deleted.
        # Let's check BaseDBModel first or assume it from previous logs.
        # "BaseDBModel for shared fields like IDs, timestamps, and soft delete flags." -> Yes.
        db_obj.is_deleted = True
        db.add(db_obj)
        await db.commit()
