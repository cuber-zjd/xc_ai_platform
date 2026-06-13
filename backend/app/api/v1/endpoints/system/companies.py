from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.system.sys_company import SysCompany
from app.models.system.sys_user import SysUser
from app.schemas.result import Result
from app.schemas.system.company import CompanyOptionRead

router = APIRouter()


@router.get("", response_model=Result[list[CompanyOptionRead]])
async def list_companies(
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """获取系统公司选项。"""
    _ = current_user
    statement = select(SysCompany).where(SysCompany.is_deleted == 0).order_by(SysCompany.order, SysCompany.id)
    rows = (await db.exec(statement)).all()
    items = [
        CompanyOptionRead(
            id=row.id or 0,
            name=row.name,
            code=row.code,
            sync_id=row.sync_id,
            parent_id=row.parent_id,
        )
        for row in rows
        if row.id is not None
    ]
    return Result.success(data=items)
