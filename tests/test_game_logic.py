import unittest
from unittest.mock import patch

from game_logic import GameResult, Lobby


class LobbyGameLogicTests(unittest.TestCase):
    def setUp(self):
        self.lobby = Lobby("1234", organizer_id=999, organizer_username="org")
        self.lobby.add_player(1, "alice")
        self.lobby.add_player(2, "bob")
        self.lobby.add_player(3, "carol")

    def test_set_player_name_before_and_during_game(self):
        self.assertTrue(self.lobby.set_player_name(1, "Agent A"))
        self.assertEqual(self.lobby.get_player(1).display_name, "Agent A")

        self.lobby.game_started = True
        self.assertFalse(self.lobby.set_player_name(1, "New Name"))
        self.assertEqual(self.lobby.get_player(1).display_name, "Agent A")

    def test_add_custom_workplace_rejects_duplicates(self):
        self.assertTrue(self.lobby.add_custom_workplace("Коворкинг"))
        self.assertIn("Коворкинг", self.lobby.custom_workplaces)

        self.assertFalse(self.lobby.add_custom_workplace("Коворкинг"))
        self.assertFalse(self.lobby.add_custom_workplace(self.lobby.WORKPLACES[0]))

    def test_start_game_assigns_one_spy_and_workplace_for_workers(self):
        with patch("game_logic.random.choice", side_effect=["Банк", self.lobby.players[1]]):
            started = self.lobby.start_game()

        self.assertTrue(started)
        self.assertTrue(self.lobby.game_started)
        self.assertEqual(self.lobby.current_workplace, "Банк")
        self.assertEqual(self.lobby.spy.user_id, 2)

        spies = [p for p in self.lobby.players if p.is_spy]
        workers = [p for p in self.lobby.players if not p.is_spy]
        self.assertEqual(len(spies), 1)
        self.assertTrue(all(w.workplace == "Банк" for w in workers))
        self.assertIsNone(spies[0].workplace)

    def test_spy_guess_and_vote_result_majority_yes(self):
        with patch("game_logic.random.choice", side_effect=["Школа", self.lobby.players[0]]):
            self.assertTrue(self.lobby.start_game())

        spy = self.lobby.spy
        workers = self.lobby.get_workers()

        self.assertTrue(self.lobby.stop_game_by_spy(spy.user_id))
        self.assertTrue(self.lobby.set_spy_guess("Школа"))
        self.assertTrue(self.lobby.vote(workers[0].user_id, True))
        self.assertTrue(self.lobby.vote(workers[1].user_id, True))
        self.assertEqual(self.lobby.get_vote_result(), "spy_win")

    def test_end_game_resets_round_state(self):
        with patch("game_logic.random.choice", side_effect=["Театр", self.lobby.players[2]]):
            self.assertTrue(self.lobby.start_game())
        self.lobby.stop_game_by_spy(self.lobby.spy.user_id)
        self.lobby.set_spy_guess("Театр")
        self.lobby.end_game(GameResult.WORKERS_WIN)

        self.assertFalse(self.lobby.game_started)
        self.assertFalse(self.lobby.game_stopped)
        self.assertIsNone(self.lobby.current_workplace)
        self.assertIsNone(self.lobby.spy)
        self.assertEqual(self.lobby.votes, {})
        self.assertTrue(all(not p.is_spy for p in self.lobby.players))
        self.assertTrue(all(p.workplace is None for p in self.lobby.players))


if __name__ == "__main__":
    unittest.main()
