"""Единая прикладная точка управления игровыми лобби.

``game/`` по-прежнему содержит только синхронные правила игры. Этот модуль
серилизует действия одного лобби, хранит итог последнего раунда и сообщает
адаптерам о произошедших изменениях.
"""
import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from game.game_logic import GameManager, GameResult, Lobby


@dataclass(frozen=True)
class GameEvent:
    kind: str
    lobby_id: str
    actor_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    error: Optional[str] = None
    event: Optional[GameEvent] = None


EventListener = Callable[[GameEvent], Awaitable[None]]


class GameCoordinator:
    """Общий in-memory runtime для веба и Telegram в одном процессе."""

    def __init__(self, game_manager: Optional[GameManager] = None):
        self.game_manager = game_manager or GameManager()
        self.last_results: Dict[str, dict] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._listeners: List[EventListener] = []
        self._disconnect_tasks: Dict[tuple[str, str], asyncio.Task] = {}

    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def get_lobby(self, lobby_id: str) -> Optional[Lobby]:
        return self.game_manager.get_lobby(lobby_id)

    def reset(self, game_manager: Optional[GameManager] = None) -> None:
        """Тестовый хук: заменить эфемерное состояние целиком."""
        for task in self._disconnect_tasks.values():
            task.cancel()
        self._disconnect_tasks.clear()
        self.game_manager = game_manager or GameManager()
        self.last_results.clear()
        self._locks.clear()

    async def create_lobby(self, user_id: str, name: str, provider: str, source: str = "web") -> str:
        lobby_id = self.game_manager.create_lobby(user_id, name)
        lobby = self.game_manager.get_lobby(lobby_id)
        # Создатель всегда игрок: это устраняет расхождение между web и bot.
        lobby.add_player(user_id, name, name)
        await self._ensure_user(user_id, name, provider)
        await self._emit(GameEvent("lobby_changed", lobby_id, user_id,
                                   {"change": "created", "origin": source}))
        return lobby_id

    async def join_lobby(self, lobby_id: str, user_id: str, name: str, provider: str,
                         source: str = "web") -> ActionResult:
        lobby = self.get_lobby(lobby_id)
        if not lobby:
            return ActionResult(False, "Лобби не найдено")
        async with self._lock(lobby_id):
            self.cancel_disconnect_reservation(lobby_id, user_id)
            if lobby.get_player(user_id):
                await self._ensure_user(user_id, name, provider)
                return ActionResult(True)
            if not lobby.add_player(user_id, name, name):
                return ActionResult(False, "Игра уже началась, нельзя присоединиться")
            await self._ensure_user(user_id, name, provider)
            event = GameEvent("lobby_changed", lobby_id, user_id,
                              {"change": "joined", "name": name, "origin": source})
            await self._emit(event)
            return ActionResult(True, event=event)

    async def leave_lobby(self, lobby_id: str, user_id: str, source: str = "web") -> ActionResult:
        lobby = self.get_lobby(lobby_id)
        if not lobby:
            return ActionResult(False, "Лобби не найдено")
        async with self._lock(lobby_id):
            self.cancel_disconnect_reservation(lobby_id, user_id)
            player = lobby.get_player(user_id)
            if not player:
                return ActionResult(False, "Вы не находитесь в этом лобби")
            if not lobby.remove_player(user_id):
                return ActionResult(False, "Нельзя покинуть лобби во время игры")
            event = GameEvent("lobby_changed", lobby_id, user_id,
                              {"change": "left", "name": player.display_name, "origin": source})
            await self._emit(event)
            return ActionResult(True, event=event)

    async def act(self, lobby_id: str, user_id: str, action: str, source: str = "web",
                  **data: Any) -> ActionResult:
        lobby = self.get_lobby(lobby_id)
        if not lobby:
            return ActionResult(False, "Лобби не найдено")

        async with self._lock(lobby_id):
            event: Optional[GameEvent] = None
            is_host = lobby.is_organizer(user_id)

            if action == "set_name":
                name = str(data.get("name", "")).strip()[:30]
                if not name or not lobby.set_player_name(user_id, name):
                    return ActionResult(False, "Нельзя изменить имя")
                event = GameEvent("lobby_changed", lobby_id, user_id,
                                  {"change": "renamed", "name": name, "origin": source})
            elif action == "add_place":
                place = str(data.get("place", "")).strip()[:50]
                if not place or not lobby.add_custom_workplace(place):
                    return ActionResult(False, "Это место уже есть или игра уже идёт")
                event = GameEvent("lobby_changed", lobby_id, user_id,
                                  {"change": "place_added", "place": place, "origin": source})
            elif action == "start":
                if not is_host:
                    return ActionResult(False, "Только организатор может начать игру")
                self.last_results.pop(lobby_id, None)
                if not lobby.start_game():
                    return ActionResult(False, "Нужно минимум 3 игрока")
                event = GameEvent("round_started", lobby_id, user_id, {"origin": source})
            elif action == "stop_spy":
                if not lobby.stop_game_by_spy(user_id):
                    return ActionResult(False, "Сейчас нельзя остановить игру")
                event = GameEvent("spy_stopped", lobby_id, user_id, {"origin": source})
            elif action == "guess":
                place = str(data.get("place", "")).strip()[:50]
                if not place or not lobby.set_spy_guess(place):
                    return ActionResult(False, "Не удалось назвать место")
                event = GameEvent("voting_started", lobby_id, user_id, {"guess": place, "origin": source})
            elif action == "accuse":
                result = lobby.stop_game_by_worker(user_id, str(data.get("target_id", "")))
                if not result:
                    return ActionResult(False, "Не удалось обвинить игрока")
                event = await self._resolve_round(lobby, result, user_id, source)
            elif action == "vote":
                if not lobby.vote(user_id, bool(data.get("value"))):
                    return ActionResult(False, "Не удалось проголосовать")
                result = lobby.get_vote_result()
                event = await self._resolve_round(lobby, result, user_id, source) if result else GameEvent(
                    "vote_recorded", lobby_id, user_id, {"origin": source})
            elif action == "win":
                winner = data.get("winner")
                if not is_host or not lobby.game_started or winner not in ("workers", "spy"):
                    return ActionResult(False, "Нельзя объявить победителя")
                result = GameResult.WORKERS_WIN if winner == "workers" else GameResult.SPY_WIN
                event = await self._resolve_round(lobby, result, user_id, source)
            elif action == "endgame":
                if not is_host or not lobby.game_started:
                    return ActionResult(False, "Нельзя завершить игру")
                self.last_results.pop(lobby_id, None)
                lobby.end_game(GameResult.WORKERS_WIN)
                event = GameEvent("round_cancelled", lobby_id, user_id, {"origin": source})
            elif action == "close":
                if not is_host:
                    return ActionResult(False, "Только организатор может закрыть лобби")
                self.game_manager.delete_lobby(lobby_id)
                event = GameEvent("lobby_closed", lobby_id, user_id, {"origin": source})
            else:
                return ActionResult(False, "Неизвестное действие")

            await self._emit(event)
            return ActionResult(True, event=event)

    def schedule_web_disconnect(self, lobby_id: str, user_id: str, seconds: int = 60) -> None:
        """Зарезервировать место веб-игрока в ожидании краткого reconnect."""
        self.cancel_disconnect_reservation(lobby_id, user_id)
        task = asyncio.create_task(self._expire_web_seat(lobby_id, user_id, seconds))
        self._disconnect_tasks[(lobby_id, user_id)] = task

    def cancel_disconnect_reservation(self, lobby_id: str, user_id: str) -> None:
        task = self._disconnect_tasks.pop((lobby_id, user_id), None)
        if task:
            task.cancel()

    async def _expire_web_seat(self, lobby_id: str, user_id: str, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            lobby = self.get_lobby(lobby_id)
            if not lobby:
                return
            async with self._lock(lobby_id):
                player = lobby.get_player(user_id)
                if not lobby.game_started and player and lobby.remove_player(user_id):
                    await self._emit(GameEvent("lobby_changed", lobby_id, user_id,
                                               {"change": "expired", "name": player.display_name,
                                                "origin": "web"}))
        except asyncio.CancelledError:
            pass
        finally:
            self._disconnect_tasks.pop((lobby_id, user_id), None)

    async def _resolve_round(self, lobby: Lobby, result: GameResult, actor_id: str,
                             source: str) -> GameEvent:
        winner = result.value
        snapshot = self._result_snapshot(lobby, winner)
        self.last_results[lobby.lobby_id] = snapshot
        participants = [
            {
                "user_id": player.user_id,
                "name": player.display_name,
                "role": "spy" if player.is_spy else "worker",
                "is_winner": (winner == "spy") == player.is_spy,
            }
            for player in lobby.players
        ]
        try:
            from persistence import stats_service
            await stats_service.record_game(
                lobby.lobby_id, lobby.current_workplace, winner,
                lobby.spy.user_id if lobby.spy else None, lobby.guessed_workplace, participants)
        except Exception as exc:
            # Неполадки статистики не могут оставлять раунд незавершённым.
            print(f"Не удалось записать статистику: {exc}", file=sys.stderr)
        lobby.end_game(result)
        return GameEvent("round_finished", lobby.lobby_id, actor_id,
                         {"result": snapshot, "origin": source})

    async def _ensure_user(self, user_id: str, name: str, provider: str) -> None:
        try:
            from persistence import stats_service
            await stats_service.ensure_user(user_id, name, provider)
        except Exception as exc:
            print(f"Не удалось сохранить пользователя: {exc}", file=sys.stderr)

    def _lock(self, lobby_id: str) -> asyncio.Lock:
        return self._locks.setdefault(lobby_id, asyncio.Lock())

    async def _emit(self, event: GameEvent) -> None:
        for listener in list(self._listeners):
            try:
                await listener(event)
            except Exception as exc:
                print(f"Не удалось доставить событие {event.kind}: {exc}", file=sys.stderr)

    @staticmethod
    def _result_snapshot(lobby: Lobby, winner: str) -> dict:
        yes_votes = no_votes = None
        if lobby.votes:
            yes_votes = sum(1 for vote in lobby.votes.values() if vote)
            no_votes = len(lobby.votes) - yes_votes
        return {
            "winner": winner,
            "spy_name": lobby.spy.display_name if lobby.spy else "—",
            "workplace": lobby.current_workplace,
            "guessed_workplace": lobby.guessed_workplace,
            "accused_name": lobby.accused_player.display_name if lobby.accused_player else None,
            "yes_votes": yes_votes,
            "no_votes": no_votes,
        }
