from typing import Any, List
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api import deps
from app.db.session import get_db
from app.models.system.sys_user import SysUser
from app.schemas.result import Result
from app.schemas.system.dept import DeptTreeNode
from app.services.system.dept_service import DeptService

router = APIRouter()

@router.get("/tree", response_model=Result[List[DeptTreeNode]])
async def get_dept_tree(
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """
    获取部门树形结构
    """
    tree = await DeptService.get_tree(db)
    return Result.success(data=tree)
