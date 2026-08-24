"""Общая база для тестов веб-адаптера: временная БД + запуск lifespan.

Не начинается с ``test_``, поэтому unittest не подхватывает её как набор тестов.
"""
import os
import tempfile
import unittest
import uuid

try:
    from fastapi.testclient import TestClient
    import sqlalchemy  # noqa: F401
    HAS_DEPS = True
except ModuleNotFoundError:
    HAS_DEPS = False

if HAS_DEPS:
    from adapters.web import app as webapp
    from persistence import db
    from game.game_logic import GameManager


def guest_id(label):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"spy-game-test:{label}"))


def canonical_web_id(label):
    return f"web:{guest_id(label)}"


def drain(ws, n):
    """Прочитать ровно n сообщений и вернуть последнее состояние.

    Каждое действие/подключение шлёт ровно одно состояние каждому сокету в лобби,
    поэтому количество сообщений детерминировано."""
    state = None
    for _ in range(n):
        msg = ws.receive_json()
        if msg["type"] == "state":
            state = msg
    return state


@unittest.skipUnless(HAS_DEPS, "fastapi/sqlalchemy not installed")
class WebTestBase(unittest.TestCase):
    def setUp(self):
        # Чистое состояние на каждый тест (модульные глобалы переиспользуются)
        webapp.coordinator.reset(GameManager())
        webapp.game_manager = webapp.coordinator.game_manager

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        db.configure(f"sqlite+aiosqlite:///{self._tmp.name}")

        self.client = TestClient(webapp.app)
        self.client.__enter__()  # запускает lifespan -> init_db (создаёт таблицы)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        os.unlink(self._tmp.name)

    def create_lobby(self, user_id, name):
        res = self.client.post("/api/lobby", json={"user_id": guest_id(user_id), "name": name})
        self.assertEqual(res.status_code, 200)
        return res.json()["lobby_id"]

    def ws(self, lobby_id, uid, name):
        return self.client.websocket_connect(f"/ws/{lobby_id}?user_id={guest_id(uid)}&name={name}")
