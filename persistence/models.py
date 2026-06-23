"""Схема БД для статистики.

Храним сырые записи (User, Game, GamePlayer); агрегаты (побед/поражений)
считаются запросом на чтение в ``stats_service`` — так нет риска рассинхрона
материализованной таблицы.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from persistence.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # гостевой UUID
    display_name: Mapped[str] = mapped_column(String, default="Игрок")
    auth_provider: Mapped[str] = mapped_column(String, default="guest")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lobby_id: Mapped[str] = mapped_column(String)
    workplace: Mapped[str] = mapped_column(String, nullable=True)
    winner: Mapped[str] = mapped_column(String)  # "workers" | "spy"
    spy_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=True)
    guessed_workplace: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class GamePlayer(Base):
    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String)  # "spy" | "worker"
    is_winner: Mapped[bool] = mapped_column(Boolean)
