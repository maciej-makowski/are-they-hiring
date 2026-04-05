from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings


def get_session_factory(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(url or settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
