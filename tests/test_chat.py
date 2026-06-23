from web_base import WebTestBase, drain


class ChatTests(WebTestBase):
    def test_chat_is_broadcast_to_all_players(self):
        lobby_id = self.create_lobby("host", "Хост")

        with self.ws(lobby_id, "host", "Хост") as a, self.ws(lobby_id, "p2", "Боб") as b:
            # Слить состояния от подключений: a видит 2, b — 1
            drain(a, 2)
            drain(b, 1)

            a.send_json({"action": "chat", "text": "Всем привет"})

            # Чат рассылается всем — каждый сокет получает ровно одно chat-сообщение
            for sock in (a, b):
                msg = sock.receive_json()
                self.assertEqual(msg["type"], "chat")
                self.assertEqual(msg["name"], "Хост")
                self.assertEqual(msg["text"], "Всем привет")
                self.assertEqual(msg["user_id"], "host")

    def test_blank_chat_is_ignored(self):
        lobby_id = self.create_lobby("host", "Хост")
        with self.ws(lobby_id, "host", "Хост") as a:
            drain(a, 1)
            a.send_json({"action": "chat", "text": "   "})
            # Пустое сообщение не рассылается; следующее — нормальное
            a.send_json({"action": "chat", "text": "ок"})
            msg = a.receive_json()
            self.assertEqual(msg["type"], "chat")
            self.assertEqual(msg["text"], "ок")
