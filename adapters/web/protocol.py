"""Сериализация состояния лобби для фронтенда.

``build_state`` строит персональный снимок для конкретного игрока — роли видны
только их владельцу (шпион не знает место работы, работник не знает, кто шпион).
Фронт просто перерисовывается на каждое такое сообщение.
"""
from typing import Optional

from game.game_logic import Lobby

MIN_PLAYERS = 3


def lobby_status(lobby: Lobby, last_result: Optional[dict]) -> str:
    if not lobby.game_started:
        return "finished" if last_result else "waiting"
    if lobby.guessed_workplace:
        return "voting"
    return "playing"


def build_state(lobby: Lobby, last_result: Optional[dict], user_id: str) -> dict:
    status = lobby_status(lobby, last_result)
    me = lobby.get_player(user_id)

    data = {
        "type": "state",
        "lobby_id": lobby.lobby_id,
        "status": status,
        "is_host": lobby.is_organizer(user_id),
        "organizer": lobby.organizer_username,
        "min_players": MIN_PLAYERS,
        "players": [
            {"id": p.user_id, "name": p.display_name, "is_you": p.user_id == user_id}
            for p in lobby.players
        ],
        "custom_workplaces": list(lobby.custom_workplaces),
        "workplaces_count": len(lobby.get_all_workplaces()),
    }

    if status in ("playing", "voting"):
        data["game_stopped"] = lobby.game_stopped
        data["spy_guessing"] = lobby.game_stopped and not lobby.guessed_workplace
        if me:
            data["role"] = "spy" if me.is_spy else "worker"
            data["workplace"] = me.workplace  # None для шпиона

    if status == "voting":
        workers = lobby.get_workers()
        data["guessed_workplace"] = lobby.guessed_workplace
        data["votes_count"] = len(lobby.votes)
        data["workers_count"] = len(workers)
        data["you_voted"] = user_id in lobby.votes
        data["can_vote"] = bool(me and not me.is_spy)

    if status == "finished":
        data["result"] = last_result

    return data


def build_error(message: str) -> dict:
    return {"type": "error", "message": message}


def result_snapshot(lobby: Lobby, winner: str) -> dict:
    """Снимок итога раунда. Снимается ДО ``end_game`` (тот обнуляет роли/место)."""
    yes_votes = no_votes = None
    if lobby.votes:
        yes_votes = sum(1 for v in lobby.votes.values() if v)
        no_votes = len(lobby.votes) - yes_votes

    return {
        "winner": winner,  # "workers" | "spy"
        "spy_name": lobby.spy.display_name if lobby.spy else "—",
        "workplace": lobby.current_workplace,
        "guessed_workplace": lobby.guessed_workplace,
        "accused_name": lobby.accused_player.display_name if lobby.accused_player else None,
        "yes_votes": yes_votes,
        "no_votes": no_votes,
    }
