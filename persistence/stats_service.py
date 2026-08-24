"""Сервис статистики. Вызывается только из веб-адаптера (``_resolve_round``),
чтобы игровая логика в ``game/`` оставалась чистой и не знала про БД.
"""
from typing import List, Optional

from sqlalchemy import func, select

from persistence import db
from persistence.models import Game, GamePlayer, User


async def ensure_user(user_id: str, display_name: str, auth_provider: str = "guest") -> None:
    async with db.session() as s:
        user = await s.get(User, user_id)
        if user is None:
            s.add(User(id=user_id, display_name=display_name, auth_provider=auth_provider))
        elif display_name:
            user.display_name = display_name
        await s.commit()


async def record_game(
    lobby_id: str,
    workplace: Optional[str],
    winner: str,
    spy_user_id: Optional[str],
    guessed_workplace: Optional[str],
    participants: List[dict],
) -> None:
    """Записать завершённый раунд. ``participants`` — список
    ``{user_id, name, role, is_winner}``."""
    async with db.session() as s:
        for p in participants:
            user = await s.get(User, p["user_id"])
            if user is None:
                s.add(User(id=p["user_id"], display_name=p["name"]))
            elif p["name"]:
                user.display_name = p["name"]

        game = Game(
            lobby_id=lobby_id,
            workplace=workplace,
            winner=winner,
            spy_user_id=spy_user_id,
            guessed_workplace=guessed_workplace,
        )
        s.add(game)
        await s.flush()  # получить game.id

        for p in participants:
            s.add(GamePlayer(
                game_id=game.id,
                user_id=p["user_id"],
                role=p["role"],
                is_winner=p["is_winner"],
            ))
        await s.commit()


async def get_stats(user_id: str) -> dict:
    async with db.session() as s:
        def _count(*conditions):
            return select(func.count()).select_from(GamePlayer).where(
                GamePlayer.user_id == user_id, *conditions)

        games = await s.scalar(_count()) or 0
        wins = await s.scalar(_count(GamePlayer.is_winner.is_(True))) or 0
        times_spy = await s.scalar(_count(GamePlayer.role == "spy")) or 0
        spy_wins = await s.scalar(
            _count(GamePlayer.role == "spy", GamePlayer.is_winner.is_(True))) or 0
        name = await s.scalar(select(User.display_name).where(User.id == user_id))

        return {
            "user_id": user_id,
            "display_name": name,
            "games": games,
            "wins": wins,
            "losses": games - wins,
            "times_spy": times_spy,
            "spy_wins": spy_wins,
        }
