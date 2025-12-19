from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.models.system.sys_user import SysUser
from app.schemas.result import Result

router = APIRouter()

@router.post("/login/access-token", response_model=Result[Any])
async def login_access_token(
    db: AsyncSession = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # 1. Simple auth by username
    query = select(SysUser).where(SysUser.username == form_data.username)
    result = await db.exec(query)
    user = result.first()

    # 2. Verify password (if user exists, has pwd, etc)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        # Return standard Result fail instead of 400 for consistency if prefered, 
        # but OAuth spec usually expects 400. 
        # Using BizException or just HTTP 400. Let's stick to HTTP 400 for Token URL compliance.
        raise HTTPException(status_code=400, detail="Incorrect email or password")
        
    if user.status != 1:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    
    return Result.success(data={
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": "admin" if user.is_superuser else "user"
        }
    })

@router.post("/login/test-token", response_model=Result[Any])
async def test_token(current_user: SysUser = Depends(deps.get_current_user)) -> Any:
    """
    Test access token
    """
    return Result.success(data=current_user)
