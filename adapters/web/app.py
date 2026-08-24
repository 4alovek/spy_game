"""FastAPI-адаптер общего кроссплатформенного runtime игры."""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from adapters.web import protocol
from adapters.web.ws_manager import ConnectionManager
from application.coordinator import GameCoordinator, GameEvent
from application.identity import web_user_id
from persistence import db, stats_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    telegram_application = None
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        # Один event loop и один GameCoordinator: Telegram и WebSocket видят
        # одинаковое in-memory состояние лобби.
        from adapters.telegram.bot import build_application
        telegram_application = build_application(coordinator)
        await telegram_application.initialize()
        await telegram_application.start()
        await telegram_application.updater.start_polling()
        app.state.telegram_application = telegram_application
    else:
        print("TELEGRAM_BOT_TOKEN не задан: запущен только веб-режим", file=sys.stderr)
    try:
        yield
    finally:
        if telegram_application:
            await telegram_application.updater.stop()
            await telegram_application.stop()
            await telegram_application.shutdown()


app = FastAPI(title="Spy Game", lifespan=lifespan)
coordinator = GameCoordinator()
# Обратные ссылки полезны существующим тестам и интерактивной отладке.
game_manager = coordinator.game_manager
last_results = coordinator.last_results
manager = ConnectionManager()

# lobby_id -> множество канонических user_id в голосовом чате
voice_members: Dict[str, set] = {}
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class CreateLobbyRequest(BaseModel):
    user_id: str
    name: str


async def _broadcast_state(lobby_id: str) -> None:
    lobby = coordinator.get_lobby(lobby_id)
    if lobby:
        await manager.broadcast(
            lobby_id,
            lambda user_id: protocol.build_state(lobby, coordinator.last_results.get(lobby_id), user_id),
        )


async def _on_game_event(event: GameEvent) -> None:
    """Web-проекция каждого игрового события — обновлённый личный state."""
    if event.kind != "lobby_closed":
        await _broadcast_state(event.lobby_id)


coordinator.subscribe(_on_game_event)
app.state.coordinator = coordinator


@app.get("/healthz")
async def healthz():
    """Лёгкая readiness-проверка для будущего Docker healthcheck."""
    try:
        async with db.session() as session:
            await session.connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc
    return {"status": "ok"}


@app.post("/api/lobby")
async def create_lobby(req: CreateLobbyRequest):
    try:
        user_id = web_user_id(req.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    lobby_id = await coordinator.create_lobby(user_id, req.name.strip()[:30] or "Хост", "guest")
    return {"lobby_id": lobby_id}


@app.get("/api/lobby/{lobby_id}")
async def check_lobby(lobby_id: str):
    lobby = coordinator.get_lobby(lobby_id)
    if not lobby:
        return {"exists": False}
    return {"exists": True, "started": lobby.game_started, "players": len(lobby.players)}


@app.get("/api/users/{user_id}/stats")
async def user_stats(user_id: str):
    try:
        canonical_id = web_user_id(user_id)
    except ValueError:
        # Неизвестный/некорректный ID — возвращаем пустую статистику
        return {
            "user_id": user_id,
            "display_name": None,
            "games": 0,
            "wins": 0,
            "losses": 0,
            "times_spy": 0,
            "spy_wins": 0,
        }
    return await stats_service.get_stats(canonical_id)


async def _broadcast_chat(lobby_id: str, user_id: str, text: str) -> None:
    text = str(text).strip()[:300]
    lobby = coordinator.get_lobby(lobby_id)
    player = lobby.get_player(user_id) if lobby else None
    if not text or not player:
        return
    await manager.broadcast(lobby_id, lambda _uid: {
        "type": "chat", "user_id": user_id, "name": player.display_name, "text": text,
    })


async def _broadcast_voice(lobby_id: str) -> None:
    members = sorted(voice_members.get(lobby_id, set()))
    await manager.broadcast(lobby_id, lambda _uid: {"type": "voice", "members": members})


async def _handle_voice(lobby_id: str, user_id: str, msg: dict) -> None:
    action = msg.get("action")
    members = voice_members.setdefault(lobby_id, set())
    if action == "voice_join":
        members.add(user_id)
        await _broadcast_voice(lobby_id)
    elif action == "voice_leave":
        members.discard(user_id)
        await _broadcast_voice(lobby_id)
    elif action == "rtc_signal" and msg.get("to"):
        await manager.send_to(lobby_id, str(msg["to"]), {
            "type": "rtc_signal", "from": user_id, "signal": msg.get("signal"),
        })


@app.websocket("/ws/{lobby_id}")
async def game_socket(websocket: WebSocket, lobby_id: str):
    raw_user_id = websocket.query_params.get("user_id")
    name = (websocket.query_params.get("name") or "Игрок").strip()[:30] or "Игрок"
    try:
        user_id = web_user_id(raw_user_id)
    except ValueError:
        await websocket.close(code=4400)
        return

    lobby = coordinator.get_lobby(lobby_id)
    if not lobby:
        await websocket.close(code=4404)
        return
    was_member = lobby.get_player(user_id) is not None
    joined = await coordinator.join_lobby(lobby_id, user_id, name, "guest")
    if not joined.ok:
        await websocket.close(code=4403)
        return

    await manager.connect(lobby_id, user_id, websocket)
    if was_member:
        # Reconnect: все открытые вкладки получают свежий личный state.
        await _broadcast_state(lobby_id)
    else:
        # Новый игрок уже вызвал state-рассылку для остальных через событие.
        # Ему достаточно отправить один снимок без дублирования соседям.
        current = coordinator.get_lobby(lobby_id)
        await manager.send_to(lobby_id, user_id,
                              protocol.build_state(current, coordinator.last_results.get(lobby_id), user_id))

    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            if action == "chat":
                await _broadcast_chat(lobby_id, user_id, msg.get("text", ""))
                continue
            if action in ("voice_join", "voice_leave", "rtc_signal"):
                await _handle_voice(lobby_id, user_id, msg)
                continue
            if action == "leave":
                result = await coordinator.leave_lobby(lobby_id, user_id)
            else:
                payload = {key: value for key, value in msg.items() if key != "action"}
                result = await coordinator.act(lobby_id, user_id, str(action), **payload)
            if not result.ok:
                await manager.send_to(lobby_id, user_id, protocol.build_error(result.error))
            if action == "leave" and result.ok:
                manager.disconnect(lobby_id, user_id, websocket)
                await websocket.close()
                return
    except WebSocketDisconnect:
        no_connections_left = manager.disconnect(lobby_id, user_id, websocket)
        members = voice_members.get(lobby_id)
        if members and user_id in members:
            members.discard(user_id)
            await _broadcast_voice(lobby_id)
        if no_connections_left:
            coordinator.schedule_web_disconnect(lobby_id, user_id)
    except Exception as exc:
        print(f"Ошибка WebSocket {lobby_id}: {exc}", file=sys.stderr)
        manager.disconnect(lobby_id, user_id, websocket)


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
