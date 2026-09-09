"""
Reframe V7 Database Engine & Session Management
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.reframe.shared.config import settings


class Base(DeclarativeBase):
    """Base SQLAlchemy Declarative Model"""
    pass


# Async Engine & SessionMaker
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


# Sync Engine & SessionMaker (for Alembic, Background Workers, or sync tasks)
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining an asynchronous DB session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_expected_alembic_head() -> str:
    """Dynamically determines expected Alembic migration head revision."""
    try:
        from alembic.script import ScriptDirectory
        from alembic.config import Config
        import os
        ini_path = "alembic.ini"
        if not os.path.exists(ini_path):
            ini_path = os.path.join(os.path.dirname(__file__), "../../../alembic.ini")
        config = Config(ini_path)
        script = ScriptDirectory.from_config(config)
        head = script.get_current_head()
        return head or "0005_v7_auth_and_checkpoint"
    except Exception:
        return "0005_v7_auth_and_checkpoint"
