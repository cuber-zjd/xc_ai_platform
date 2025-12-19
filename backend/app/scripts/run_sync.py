import asyncio
import logging
from sqlmodel import SQLModel 
from app.db.session import engine
from app.services.hr_sync_service import HrSyncService
# Import models so SQLModel knows about them for create_all
from app.models.system.sys_user import SysUser
from app.models.system.sys_company import SysCompany
from app.models.system.sys_dept import SysDept
from app.models.system.sys_post import SysPost

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing Database tables...")
    # For now, auto-create tables if not exist. In prod, use Alembic.
    async with engine.begin() as conn:
        # Drop and recreate to apply schema changes (Dev mode)
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    
    logger.info("Triggering HR Sync...")
    # The service currently uses blocking IO (pymssql) and synchronous SQLModel Session for the sync logic
    # We should run it in a threadpool if calling from async context, but for this script direct call is fine 
    # if we change the service to be sync-compatible or wrap it.
    # The service was written with synchronous Session(engine). 
    # Wait, app.db.session.engine is likely AsyncEngine if we followed the readme standard (asyncpg).
    # Let's check session.py content to be sure.
    
    try:
        await HrSyncService.sync_all()
    except Exception as e:
        logger.error(e)

if __name__ == "__main__":
    asyncio.run(main())
