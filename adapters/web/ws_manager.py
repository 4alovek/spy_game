"""Менеджер WebSocket-соединений — веб-аналог broadcast_to_lobby в Telegram-боте.

Бот рассылает события игрокам личными сообщениями; здесь мы держим открытые
WebSocket-сокеты по лобби и рассылаем JSON тем же способом.
"""
from typing import Callable, Dict, List, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # lobby_id -> {user_id: {WebSocket, ...}}. Один игрок может открыть
        # несколько вкладок; закрытие одной не должно освобождать его место.
        self.rooms: Dict[str, Dict[str, Set[WebSocket]]] = {}

    async def connect(self, lobby_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.rooms.setdefault(lobby_id, {}).setdefault(user_id, set()).add(websocket)

    def disconnect(self, lobby_id: str, user_id: str, websocket: WebSocket) -> bool:
        """Убрать конкретный сокет и вернуть True, если у игрока их не осталось."""
        room = self.rooms.get(lobby_id)
        if not room:
            return True
        sockets = room.get(user_id)
        if not sockets:
            return True
        sockets.discard(websocket)
        if not sockets:
            room.pop(user_id, None)
        if not room:
            self.rooms.pop(lobby_id, None)
        return user_id not in room

    def user_ids(self, lobby_id: str) -> List[str]:
        return list(self.rooms.get(lobby_id, {}).keys())

    async def send_to(self, lobby_id: str, user_id: str, message: dict) -> None:
        for ws in list(self.rooms.get(lobby_id, {}).get(user_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(lobby_id, user_id, ws)

    async def broadcast(self, lobby_id: str, builder: Callable[[str], dict]) -> None:
        """Разослать всем в лобби. ``builder(user_id)`` строит персональное сообщение
        (роли спрятаны: шпион и работник видят разное)."""
        for user_id, sockets in list(self.rooms.get(lobby_id, {}).items()):
            message = builder(user_id)
            for ws in list(sockets):
                try:
                    await ws.send_json(message)
                except Exception:
                    self.disconnect(lobby_id, user_id, ws)
