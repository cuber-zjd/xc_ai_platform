from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.models.system.sys_user import SysUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token")

async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> SysUser:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = payload.get("sub")
    except (JWTError, ValidationError) as e:
        print(f"DEBUG AUTH: JWT Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
        
    try:
        if token_data is None:
             print("DEBUG AUTH: Token sub is None")
             raise ValueError("Token sub (user_id) is missing")
        user_id = int(token_data)
    except ValueError as e:
        print(f"DEBUG AUTH: Value Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user ID in token",
        )
    except Exception as e:
        print(f"DEBUG AUTH: Unexpected Error parsing token: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Auth Error",
        )

    try:
        query = select(SysUser).where(SysUser.id == user_id, SysUser.status == 1)
        result = await db.exec(query)
        user = result.first()
    except Exception as e:
        print(f"DEBUG AUTH: Database Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")
    
    if not user:
        print(f"DEBUG AUTH: User {user_id} not found in DB")
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != 1:
         raise HTTPException(status_code=400, detail="Inactive user")
         
    return user

def get_current_active_superuser(
    current_user: SysUser = Depends(get_current_user),
) -> SysUser:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="The user doesn't have enough privileges"
        )
    return current_user
