import asyncio
import sys
from sqlalchemy import text
from sqlmodel import select

from pathlib import Path

# Add backend to path (resolve relative to this file)
# This file is in .../backend/app/scripts/init_db.py
# We want .../backend/ to be in sys.path so we can import 'app'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.db.session import engine, async_session  # noqa: E402
from app.models.system.sys_user import SysUser  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402

async def init_db():
    async with engine.begin() as conn:
        # 1. Update Schema (Manual Migration for existing table)
        print("Updating Schema...")
        try:
            # Add hashed_password
            await conn.execute(text("ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS hashed_password VARCHAR DEFAULT ''"))
            # Add is_superuser
            await conn.execute(text("ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS is_superuser BOOLEAN DEFAULT FALSE"))
            print("Schema updated successfully (or already up to date).")
        except Exception as e:
            print(f"Schema update notice: {e}")

    async with async_session() as session:
        # 2. Create Superuser
        print("Checking for Superuser...")
        result = await session.exec(select(SysUser).where(SysUser.username == "admin"))
        user = result.first()
        
        if not user:
            print("Creating superuser 'admin' with password 'admin123'...")
            new_user = SysUser(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                is_superuser=True,
                full_name="Administrator",
                status=1, 
                dept_id="0",
                employee_id="admin"
            )
            session.add(new_user)
            await session.commit()
            print("Superuser created.")
        else:
            print("Superuser 'admin' already exists.")
            print("Superuser 'admin' already exists.")
            # Force update password to ensure matches current hashing scheme
            user.hashed_password = get_password_hash("admin123")
            session.add(user)
            await session.commit()
            print("Force updated admin password to current scheme.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(init_db())
