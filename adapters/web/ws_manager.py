"""Менеджер WebSocket-соединений — веб-аналог broadcast_to_lobby в Telegram-боте.

Бот рассылает события игрокам личными сообщениями; здесь мы держим открытые
WebSocket-сокеты по лобби и рассылаем JSON тем же способом.
"""
from typing import Callable, Dict, List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # lobby_id -> {user_id: WebSocket}
        self.rooms: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, lobby_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.rooms.setdefault(lobby_id, {})[user_id] = websocket

    def disconnect(self, lobby_id: str, user_id: str) -> None:
        room = self.rooms.get(lobby_id)
        if not room:
            return
        room.pop(user_id, None)
        if not room:
            self.rooms.pop(lobby_id, None)

    def user_ids(self, lobby_id: str) -> List[str]:
        return list(self.rooms.get(lobby_id, {}).keys())

    async def send_to(self, lobby_id: str, user_id: str, message: dict) -> None:
        ws = self.rooms.get(lobby_id, {}).get(user_id)
        if ws is not None:
            await ws.send_json(message)

    async def broadcast(self, lobby_id: str, builder: Callable[[str], dict]) -> None:
        """Разослать всем в лобби. ``builder(user_id)`` строит персональное сообщение
        (роли спрятаны: шпион и работник видят разное)."""
        for user_id, ws in list(self.rooms.get(lobby_id, {}).items()):
            try:
                await ws.send_json(builder(user_id))
            except Exception:
                # Мёртвый сокет — уберём его, отключение обработается в основном цикле
                self.disconnect(lobby_id, user_id)
