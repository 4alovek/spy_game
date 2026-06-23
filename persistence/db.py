"""Настройка БД (async SQLAlchemy + SQLite по умолчанию).

Движок создаётся лениво и переконфигурируется через ``configure`` — это нужно
тестам, чтобы подменить URL на временную БД. Схема создаётся через
``init_db`` (Base.metadata.create_all); миграции Alembic появятся, когда схема
начнёт меняться на проде.
"""
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DEFAULT_URL = "sqlite+aiosqlite:///spy_game.db"


class Base(DeclarativeBase):
    pass


_engine = None
_sessionmaker = None


def configure(url: str = None) -> None:
    global _engine, _sessionmaker
    url = url or os.getenv("SPY_DB_URL", DEFAULT_URL)
    _engine = create_async_engine(url)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


def session() -> AsyncSession:
    if _sessionmaker is None:
        configure()
    return _sessionmaker()


async def init_db() -> None:
    if _engine is None:
        configure()
    # Импорт моделей регистрирует их в Base.metadata
    from persistence import models  # noqa: F401
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
