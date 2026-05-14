import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone

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
os.environ.setdefault("EMAIL_PROVIDER", "mock")

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from app.core.config import get_settings
from app.core.security import hash_password
from app.core.dependencies import get_db_session
import app.models  # noqa: F401
from app.models.event import Event, EventFieldDefinition, EventState, FieldType, OverflowRule
from app.models.staff import StaffAccessMode, StaffAccessModeRecord, StaffAccount, StaffRole
from app.workers.email_tasks import send_email_task

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
def migrated_database() -> Iterator[None]:
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
async def client(async_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture
def captured_email_tasks(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    captured: list[dict] = []

    def fake_delay(payload: dict) -> dict:
        captured.append(payload)
        return payload

    monkeypatch.setattr(send_email_task, "delay", fake_delay)
    return captured


@pytest_asyncio.fixture
async def seeded_admin_account(db_session: AsyncSession) -> StaffAccount:
    account = StaffAccount(
        email="admin@eventapp.local",
        password_hash=hash_password("Admin1234!"),
        role=StaffRole.ADMIN,
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()
    db_session.add(StaffAccessModeRecord(staff_id=account.id, mode=StaffAccessMode.ALL_EVENTS))
    await db_session.commit()
    await db_session.refresh(account)
    return account


@pytest_asyncio.fixture
async def seeded_staff_account(db_session: AsyncSession) -> StaffAccount:
    account = StaffAccount(
        email="staff@eventapp.local",
        password_hash=hash_password("Staff1234!"),
        role=StaffRole.STAFF,
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()
    db_session.add(StaffAccessModeRecord(staff_id=account.id, mode=StaffAccessMode.ALL_EVENTS))
    await db_session.commit()
    await db_session.refresh(account)
    return account


@pytest_asyncio.fixture
async def disabled_staff_account(db_session: AsyncSession) -> StaffAccount:
    account = StaffAccount(
        email="disabled@eventapp.local",
        password_hash=hash_password("Disabled1234!"),
        role=StaffRole.STAFF,
        is_active=False,
    )
    db_session.add(account)
    await db_session.flush()
    db_session.add(StaffAccessModeRecord(staff_id=account.id, mode=StaffAccessMode.ALL_EVENTS))
    await db_session.commit()
    await db_session.refresh(account)
    return account


async def _create_event_fixture(
    db_session: AsyncSession,
    *,
    created_by: StaffAccount,
    title: str,
    description: str,
    event_date: datetime,
    location: str,
    prefix: str,
    price: int,
    capacity: int | None,
    overflow_rule: OverflowRule,
    state: EventState,
    custom_fields: list[EventFieldDefinition] | None = None,
) -> Event:
    event = Event(
        title=title,
        description=description,
        event_date=event_date,
        location=location,
        prefix=prefix,
        price=price,
        capacity=capacity,
        overflow_rule=overflow_rule,
        state=state,
        created_by=created_by.id,
    )
    event.field_definitions = custom_fields or []
    db_session.add(event)
    await db_session.commit()
    result = await db_session.execute(
        select(Event)
        .where(Event.id == event.id)
        .options(selectinload(Event.field_definitions))
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def seeded_free_published_event(
    db_session: AsyncSession,
    seeded_admin_account: StaffAccount,
) -> Event:
    return await _create_event_fixture(
        db_session,
        created_by=seeded_admin_account,
        title="Community Meetup 2026",
        description="A free meetup for local developers.",
        event_date=datetime(2026, 9, 5, 14, 0, tzinfo=timezone.utc),
        location="Abuja, Nigeria",
        prefix="CMT",
        price=0,
        capacity=None,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.PUBLISHED,
        custom_fields=[
            EventFieldDefinition(
                label="Phone Number",
                field_type=FieldType.PHONE,
                is_required=True,
                display_order=1,
            )
        ],
    )


@pytest_asyncio.fixture
async def seeded_paid_published_event(
    db_session: AsyncSession,
    seeded_admin_account: StaffAccount,
) -> Event:
    return await _create_event_fixture(
        db_session,
        created_by=seeded_admin_account,
        title="Tech Conference 2026",
        description="Annual technology conference for developers.",
        event_date=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
        location="Lagos, Nigeria",
        prefix="TEC",
        price=5000,
        capacity=100,
        overflow_rule=OverflowRule.WAITLIST,
        state=EventState.PUBLISHED,
        custom_fields=[
            EventFieldDefinition(
                label="Phone Number",
                field_type=FieldType.PHONE,
                is_required=True,
                display_order=1,
            ),
            EventFieldDefinition(
                label="T-Shirt Size",
                field_type=FieldType.TEXT,
                is_required=False,
                display_order=2,
            ),
        ],
    )


@pytest_asyncio.fixture
async def seeded_draft_event(
    db_session: AsyncSession,
    seeded_admin_account: StaffAccount,
) -> Event:
    return await _create_event_fixture(
        db_session,
        created_by=seeded_admin_account,
        title="Private Planning Session",
        description="Internal planning event.",
        event_date=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        location="Port Harcourt, Nigeria",
        prefix="PLN",
        price=2500,
        capacity=40,
        overflow_rule=OverflowRule.HARD_REJECTION,
        state=EventState.DRAFT,
        custom_fields=[],
    )
