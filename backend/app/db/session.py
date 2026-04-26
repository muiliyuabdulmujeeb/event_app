from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def create_engine_from_url(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


settings = get_settings()
engine = create_engine_from_url(settings.database_url)
SessionLocal = create_session_factory(engine)
