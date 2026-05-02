from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api import deps
from app.db.session import get_db
from app.models.system.sys_user import SysUser
from app.schemas.result import Result
from app.schemas.system.role import RoleRead, RoleCreate, RoleUpdate, UserRoleAssign
from app.schemas.system.user import UserRead
from app.schemas.page import Page
from app.services.system.role_service import RoleService

router = APIRouter()

@router.get("", response_model=Result[Page[RoleRead]])
async def read_roles(
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    size: int = 20,
    name: str = None,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    分页获取角色列表。
    """
    result = await RoleService.get_list(db, page=page, size=size, name=name)
    return Result.success(data=result)

@router.post("", response_model=Result[RoleRead])
async def create_role(
    *,
    db: AsyncSession = Depends(get_db),
    role_in: RoleCreate,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    创建新角色。
    """
    role = await RoleService.get_by_code(db, code=role_in.code)
    if role:
        raise HTTPException(status_code=400, detail="Role with this code already exists.")
    role = await RoleService.create(db, obj_in=role_in)
    return Result.success(data=role)

@router.put("/{role_id}", response_model=Result[RoleRead])
async def update_role(
    *,
    db: AsyncSession = Depends(get_db),
    role_id: int,
    role_in: RoleUpdate,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    更新角色。
    """
    role = await RoleService.get_by_id(db, role_id=role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    role = await RoleService.update(db, db_obj=role, obj_in=role_in)
    return Result.success(data=role)

@router.delete("/{role_id}", response_model=Result[Any])
async def delete_role(
    *,
    db: AsyncSession = Depends(get_db),
    role_id: int,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    删除角色（软删除）。
    """
    role = await RoleService.get_by_id(db, role_id=role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    await RoleService.delete(db, db_obj=role)
    return Result.success(msg="Role deleted successfully")

@router.post("/assign", response_model=Result[Any])
async def assign_user_roles(
    *,
    db: AsyncSession = Depends(get_db),
    assign_in: UserRoleAssign,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    给用户分配角色。
    """
    await RoleService.assign_to_user(db, user_id=assign_in.user_id, role_ids=assign_in.role_ids)
    return Result.success(msg="Roles assigned successfully")

@router.get("/user/{user_id}", response_model=Result[List[int]])
async def get_user_role_ids(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    获取用户的角色 ID 列表。
    """
    role_ids = await RoleService.get_user_role_ids(db, user_id=user_id)
    return Result.success(data=role_ids)

@router.get("/{role_id}/users", response_model=Result[List[int]])
async def get_role_user_ids(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    获取角色的用户 ID 列表。
    """
    user_ids = await RoleService.get_role_user_ids(db, role_id=role_id)
    return Result.success(data=user_ids)

@router.get("/{role_id}/users/details", response_model=Result[List[UserRead]])
async def get_role_users_details(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    获取角色的用户详情列表。
    """
    users = await RoleService.get_role_users(db, role_id=role_id)
    return Result.success(data=users)

@router.post("/{role_id}/users", response_model=Result[Any])
async def assign_role_users(
    role_id: int,
    user_ids: List[int],
    db: AsyncSession = Depends(get_db),
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    给角色分配用户。
    """
    await RoleService.assign_users_to_role(db, role_id=role_id, user_ids=user_ids)
    return Result.success(msg="Role users updated successfully")
