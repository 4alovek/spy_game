"""FastAPI-адаптер веб-версии «Шпиона».

Переиспользует чистую логику из ``game/`` без изменений. Реальное время —
через WebSocket: после каждого действия лобби полностью пересобирается и
рассылается всем игрокам (персонально, чтобы скрыть роли).

Идентичность — гостевая: фронт генерирует UUID и кладёт в localStorage, сервер
принимает его как ``user_id``. Здесь нет БД и статистики (это фаза 2).
"""
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game.game_logic import GameManager, GameResult
from adapters.web import protocol
from adapters.web.ws_manager import ConnectionManager

app = FastAPI(title="Spy Game")
game_manager = GameManager()
manager = ConnectionManager()

# lobby_id -> снимок итога последнего раунда (показывается до следующего старта)
last_results: Dict[str, dict] = {}

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class CreateLobbyRequest(BaseModel):
    user_id: str
    name: str


@app.post("/api/lobby")
async def create_lobby(req: CreateLobbyRequest):
    lobby_id = game_manager.create_lobby(req.user_id, req.name or "Хост")
    return {"lobby_id": lobby_id}


@app.get("/api/lobby/{lobby_id}")
async def check_lobby(lobby_id: str):
    lobby = game_manager.get_lobby(lobby_id)
    if not lobby:
        return {"exists": False}
    return {
        "exists": True,
        "started": lobby.game_started,
        "players": len(lobby.players),
    }


def _resolve_round(lobby, result_code: str) -> None:
    """Единая точка завершения раунда: снять снимок итога и сбросить лобби.

    Сюда же позже подключится запись статистики в БД (фаза 2)."""
    winner = "workers" if result_code == "workers_win" else "spy"
    last_results[lobby.lobby_id] = protocol.result_snapshot(lobby, winner)
    lobby.end_game(GameResult.WORKERS_WIN if winner == "workers" else GameResult.SPY_WIN)


async def _broadcast_state(lobby_id: str) -> None:
    lobby = game_manager.get_lobby(lobby_id)
    if not lobby:
        return
    last = last_results.get(lobby_id)
    await manager.broadcast(lobby_id, lambda uid: protocol.build_state(lobby, last, uid))


async def _handle_action(lobby, user_id: str, msg: dict) -> Optional[str]:
    """Обработать действие. Возвращает текст ошибки или None."""
    action = msg.get("action")
    is_host = lobby.is_organizer(user_id)

    if action == "set_name":
        lobby.set_player_name(user_id, str(msg.get("name", ""))[:30])
    elif action == "add_place":
        place = str(msg.get("place", "")).strip()[:50]
        if place and not lobby.add_custom_workplace(place):
            return "Это место уже есть или игра уже идёт"
    elif action == "start":
        if not is_host:
            return "Только организатор может начать игру"
        last_results.pop(lobby.lobby_id, None)
        if not lobby.start_game():
            return f"Нужно минимум {protocol.MIN_PLAYERS} игрока"
    elif action == "stop_spy":
        if not lobby.stop_game_by_spy(user_id):
            return "Сейчас нельзя остановить игру"
    elif action == "guess":
        if not lobby.set_spy_guess(str(msg.get("place", "")).strip()):
            return "Не удалось загадать место"
    elif action == "accuse":
        result = lobby.stop_game_by_worker(user_id, msg.get("target_id"))
        if not result:
            return "Не удалось обвинить игрока"
        _resolve_round(lobby, result)
    elif action == "vote":
        if not lobby.vote(user_id, bool(msg.get("value"))):
            return "Не удалось проголосовать"
        result = lobby.get_vote_result()
        if result:
            _resolve_round(lobby, result)
    elif action == "win":  # ручное решение организатора
        if not is_host:
            return "Только организатор может объявить победителя"
        if lobby.game_started:
            _resolve_round(lobby, "workers_win" if msg.get("winner") == "workers" else "spy_win")
    elif action == "endgame":  # завершить без результата
        if not is_host:
            return "Только организатор может завершить игру"
        last_results.pop(lobby.lobby_id, None)
        lobby.end_game(GameResult.WORKERS_WIN)
    else:
        return "Неизвестное действие"
    return None


@app.websocket("/ws/{lobby_id}")
async def game_socket(websocket: WebSocket, lobby_id: str):
    user_id = websocket.query_params.get("user_id")
    name = websocket.query_params.get("name") or "Игрок"

    lobby = game_manager.get_lobby(lobby_id)
    if not user_id or not lobby:
        await websocket.close(code=4404)
        return

    is_new_player = lobby.get_player(user_id) is None
    if is_new_player and lobby.game_started:
        await websocket.close(code=4403)  # игра уже идёт — не пускаем новичков
        return
    if is_new_player:
        lobby.add_player(user_id, name)

    await manager.connect(lobby_id, user_id, websocket)
    await _broadcast_state(lobby_id)

    try:
        while True:
            msg = await websocket.receive_json()
            error = await _handle_action(lobby, user_id, msg)
            if error:
                await manager.send_to(lobby_id, user_id, protocol.build_error(error))
            await _broadcast_state(lobby_id)
    except WebSocketDisconnect:
        manager.disconnect(lobby_id, user_id)
        # В режиме ожидания убираем отключившегося из лобби; во время игры
        # оставляем (позволяет переподключиться).
        if not lobby.game_started:
            lobby.remove_player(user_id)
        await _broadcast_state(lobby_id)


# Статика фронтенда (vanilla JS). Монтируется последней, чтобы не перехватывать /api и /ws.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
