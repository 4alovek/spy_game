from web_base import WebTestBase, drain, canonical_web_id


class VoiceSignalingTests(WebTestBase):
    """Тестируем серверную сигнализацию (релей). Сам WebRTC peer-to-peer
    проверяется только в браузере."""

    def test_voice_join_broadcasts_roster(self):
        lobby_id = self.create_lobby("host", "Хост")
        with self.ws(lobby_id, "host", "Хост") as a, self.ws(lobby_id, "p2", "Боб") as b:
            drain(a, 2)
            drain(b, 1)

            a.send_json({"action": "voice_join"})
            for sock in (a, b):
                msg = sock.receive_json()
                self.assertEqual(msg["type"], "voice")
                self.assertEqual(msg["members"], [canonical_web_id("host")])

            b.send_json({"action": "voice_join"})
            for sock in (a, b):
                msg = sock.receive_json()
                self.assertEqual(msg["type"], "voice")
                self.assertEqual(msg["members"], [canonical_web_id("host"), canonical_web_id("p2")])

    def test_rtc_signal_is_relayed_only_to_target(self):
        lobby_id = self.create_lobby("host", "Хост")
        with self.ws(lobby_id, "host", "Хост") as a, self.ws(lobby_id, "p2", "Боб") as b:
            drain(a, 2)
            drain(b, 1)

            # host шлёт сигнал именно p2
            a.send_json({"action": "rtc_signal", "to": canonical_web_id("p2"),
                         "signal": {"sdp": {"type": "offer", "sdp": "x"}}})
            relayed = b.receive_json()
            self.assertEqual(relayed["type"], "rtc_signal")
            self.assertEqual(relayed["from"], canonical_web_id("host"))
            self.assertEqual(relayed["signal"]["sdp"]["type"], "offer")

            # Сигнал не должен попасть отправителю: следующее, что получит host —
            # это ростер после voice_join, а не отрелеенный сигнал
            a.send_json({"action": "voice_join"})
            nxt = a.receive_json()
            self.assertEqual(nxt["type"], "voice")
            self.assertEqual(nxt["members"], [canonical_web_id("host")])

    def test_leaving_voice_updates_roster(self):
        lobby_id = self.create_lobby("host", "Хост")
        with self.ws(lobby_id, "host", "Хост") as a, self.ws(lobby_id, "p2", "Боб") as b:
            drain(a, 2)
            drain(b, 1)
            a.send_json({"action": "voice_join"})
            drain(a, 1)
            drain(b, 1)
            # p2 также присоединяется к голосовому чату
            b.send_json({"action": "voice_join"})
            drain(a, 1)
            drain(b, 1)

            a.send_json({"action": "voice_leave"})
            msg = b.receive_json()
            self.assertEqual(msg["type"], "voice")
            # p2 всё ещё в голосовом чате
            self.assertEqual(msg["members"], [canonical_web_id("p2")])
