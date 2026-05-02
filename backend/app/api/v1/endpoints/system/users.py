from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api import deps
from app.models.system.sys_user import SysUser
from app.schemas.result import Result
from app.schemas.system.user import UserRead, UserCreate, UserUpdate
from app.schemas.page import Page
from app.services.system.user_service import UserService
from app.db.session import get_db

router = APIRouter()

@router.get("/me", response_model=Result[UserRead])
async def read_user_me(
    current_user: SysUser = Depends(deps.get_current_user),
) -> Any:
    """
    Get current user.
    """
    return Result.success(data={
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": "admin" if current_user.is_superuser else "user",
        "status": current_user.status,
    })

@router.get("", response_model=Result[Page[UserRead]])
async def read_users(
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    size: int = 20,
    dept_id: int | None = None,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve users.
    """
    result = await UserService.get_list(db, page=page, size=size, dept_id=dept_id)
    return Result.success(data=result)

@router.post("", response_model=Result[UserRead])
async def create_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new user.
    """
    user = await UserService.get_by_username(db, username=user_in.username)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    user = await UserService.create(db, obj_in=user_in)
    return Result.success(data=user)

@router.put("/{user_id}", response_model=Result[UserRead])
async def update_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: str,
    user_in: UserUpdate,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a user.
    """
    user = await UserService.get_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this user_id does not exist in the system",
        )
    user = await UserService.update(db, db_obj=user, obj_in=user_in)
    return Result.success(data=user)

@router.delete("/{user_id}", response_model=Result[Any])
async def delete_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: str,
    current_user: SysUser = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a user.
    """
    user = await UserService.get_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this user_id does not exist in the system",
        )
    await UserService.delete(db, db_obj=user)
    return Result.success(msg="User deleted successfully")
