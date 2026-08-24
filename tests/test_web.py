from web_base import WebTestBase, canonical_web_id, drain


class WebAdapterTests(WebTestBase):
    def test_create_and_check_lobby(self):
        lobby_id = self.create_lobby("host", "Хост")
        res = self.client.get(f"/api/lobby/{lobby_id}").json()
        self.assertTrue(res["exists"])
        self.assertFalse(res["started"])

        self.assertFalse(self.client.get("/api/lobby/0000").json()["exists"])

    def test_full_round_worker_accuses_spy(self):
        from adapters.web import app as webapp

        lobby_id = self.create_lobby("host", "Хост")

        with self.ws(lobby_id, "host", "Хост") as a, \
                self.ws(lobby_id, "p2", "Боб") as b, \
                self.ws(lobby_id, "p3", "Кэрол") as c:
            socks = {canonical_web_id("host"): a, canonical_web_id("p2"): b, canonical_web_id("p3"): c}
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
