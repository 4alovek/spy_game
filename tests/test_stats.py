from web_base import WebTestBase, drain


class StatsTests(WebTestBase):
    def test_stats_empty_for_unknown_user(self):
        stats = self.client.get("/api/users/nobody/stats").json()
        self.assertEqual(stats["games"], 0)
        self.assertEqual(stats["wins"], 0)
        self.assertEqual(stats["losses"], 0)

    def test_round_records_stats_for_all_players(self):
        from adapters.web import app as webapp

        lobby_id = self.create_lobby("host", "Хост")

        with self.ws(lobby_id, "host", "Хост") as a, \
                self.ws(lobby_id, "p2", "Боб") as b, \
                self.ws(lobby_id, "p3", "Кэрол") as c:
            socks = {"host": a, "p2": b, "p3": c}
            drain(a, 3)
            drain(b, 2)
            drain(c, 1)

            a.send_json({"action": "start"})
            for s, n in ((a, 1), (b, 1), (c, 1)):
                drain(s, n)

            lobby = webapp.game_manager.get_lobby(lobby_id)
            spy_id = lobby.spy.user_id
            accuser_id = next(uid for uid in socks if uid != spy_id)

            # Работник верно обвиняет шпиона -> победа работников
            socks[accuser_id].send_json({"action": "accuse", "target_id": spy_id})
            drain(socks[accuser_id], 1)

        # Шпион проиграл
        spy = self.client.get(f"/api/users/{spy_id}/stats").json()
        self.assertEqual(spy["games"], 1)
        self.assertEqual(spy["wins"], 0)
        self.assertEqual(spy["losses"], 1)
        self.assertEqual(spy["times_spy"], 1)
        self.assertEqual(spy["spy_wins"], 0)

        # Работник победил
        worker_id = next(uid for uid in socks if uid != spy_id)
        worker = self.client.get(f"/api/users/{worker_id}/stats").json()
        self.assertEqual(worker["games"], 1)
        self.assertEqual(worker["wins"], 1)
        self.assertEqual(worker["losses"], 0)
        self.assertEqual(worker["times_spy"], 0)
