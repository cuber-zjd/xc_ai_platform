from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Assuming settings has DATABASE_URL. 
# If config.py doesn't exist (likely, as db/session.py didn't), we'll need to strictly check imports.
# For now, I'll hardcode or use a robust get_engine function.

# Use settings from config
DATABASE_URL = str(settings.sqlalchemy_database_uri)

engine = create_async_engine(DATABASE_URL, echo=True, future=True)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db() -> AsyncSession:
    """
    Dependency for getting an async database session.
    Yields the session and ensures it's closed after use.
    """
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
