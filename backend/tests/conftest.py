import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/eventdb",
)
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/eventdb_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "changeme")
os.environ.setdefault("JWT_ACCESS_EXPIRY_HOURS", "1")
os.environ.setdefault("JWT_REFRESH_EXPIRY_DAYS", "7")

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from app.core.config import get_settings

get_settings.cache_clear()

from app.main import app
from app.db.base import Base


TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
SYNC_TEST_DATABASE_URL = TEST_DATABASE_URL.replace("+asyncpg", "")


def build_alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    command.upgrade(build_alembic_config(), "head")
    yield


@pytest_asyncio.fixture
async def async_engine(migrated_database: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL, future=True, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def sync_engine(migrated_database: None):
    engine = create_engine(SYNC_TEST_DATABASE_URL, future=True, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def reset_database(async_engine: AsyncEngine) -> AsyncIterator[None]:
    table_names = [table.name for table in reversed(Base.metadata.sorted_tables)]
    if table_names:
        joined_names = ", ".join(table_names)
        async with async_engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE TABLE {joined_names} RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
