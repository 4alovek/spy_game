import unittest

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ModuleNotFoundError:
    HAS_FASTAPI = False

if HAS_FASTAPI:
    from adapters.web import app as webapp


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


@unittest.skipUnless(HAS_FASTAPI, "fastapi is not installed")
class WebAdapterTests(unittest.TestCase):
    def setUp(self):
        # Чистое состояние на каждый тест (модульные глобалы переиспользуются)
        from game.game_logic import GameManager
        webapp.game_manager = GameManager()
        webapp.last_results.clear()
        self.client = TestClient(webapp.app)

    def _create(self, user_id, name):
        res = self.client.post("/api/lobby", json={"user_id": user_id, "name": name})
        self.assertEqual(res.status_code, 200)
        return res.json()["lobby_id"]

    def test_create_and_check_lobby(self):
        lobby_id = self._create("host", "Хост")
        res = self.client.get(f"/api/lobby/{lobby_id}").json()
        self.assertTrue(res["exists"])
        self.assertFalse(res["started"])

        self.assertFalse(self.client.get("/api/lobby/0000").json()["exists"])

    def test_full_round_worker_accuses_spy(self):
        lobby_id = self._create("host", "Хост")

        def ws(uid, name):
            return self.client.websocket_connect(
                f"/ws/{lobby_id}?user_id={uid}&name={name}"
            )

        with ws("host", "Хост") as a, ws("p2", "Боб") as b, ws("p3", "Кэрол") as c:
            socks = {"host": a, "p2": b, "p3": c}
            # Каждое подключение рассылает всем уже подключённым: a видит 3, b — 2, c — 1
            drain(a, 3)
            drain(b, 2)
            drain(c, 1)

            a.send_json({"action": "start"})
            state = drain(a, 1)
            drain(b, 1)
            drain(c, 1)
            self.assertEqual(state["status"], "playing")

            lobby = webapp.game_manager.get_lobby(lobby_id)
            spy_id = lobby.spy.user_id
            accuser_id = next(uid for uid in socks if uid != spy_id)

            # Работник обвиняет настоящего шпиона -> победа работников
            socks[accuser_id].send_json({"action": "accuse", "target_id": spy_id})
            final = drain(socks[accuser_id], 1)
            self.assertEqual(final["status"], "finished")
            self.assertEqual(final["result"]["winner"], "workers")
            self.assertIsNotNone(final["result"]["workplace"])


if __name__ == "__main__":
    unittest.main()
