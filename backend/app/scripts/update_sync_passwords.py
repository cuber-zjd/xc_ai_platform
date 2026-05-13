import asyncio
import sys
from pathlib import Path

# Add backend to path (resolve relative to this file)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from sqlmodel import select  # noqa: E402
from app.db.session import async_session  # noqa: E402
from app.models.system.sys_user import SysUser  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402

async def update_passwords():
    async with async_session() as session:
        # 查找所有通过系统同步创建的用户
        statement = select(SysUser).where(SysUser.create_by == "system_sync")
        result = await session.exec(statement)
        users = result.all()
        
        default_hash = get_password_hash("xc@123456")
        count = 0
        for user in users:
            # 如果密码为空或不是合法的 argon2 格式哈希值，则将其统一设置为 xc@123456
            if not user.hashed_password or not user.hashed_password.startswith("$argon2"):
                user.hashed_password = default_hash
                session.add(user)
                count += 1
                
        if count > 0:
            await session.commit()
            print(f"成功为 {count} 个已同步的用户设置了默认初始密码：xc@123456")
        else:
            print("没有需要修复密码的用户。")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(update_passwords())
