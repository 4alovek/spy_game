import unittest
import sys
import types
from types import SimpleNamespace

try:
    import bot
except ModuleNotFoundError as exc:
    if exc.name != "telegram":
        raise

    telegram_stub = types.ModuleType("telegram")

    class Update:
        ALL_TYPES = ()

    class Bot:
        pass

    class InlineKeyboardButton:
        def __init__(self, text, callback_data=None):
            self.text = text
            self.callback_data = callback_data

    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard

    telegram_stub.Update = Update
    telegram_stub.Bot = Bot
    telegram_stub.InlineKeyboardButton = InlineKeyboardButton
    telegram_stub.InlineKeyboardMarkup = InlineKeyboardMarkup
    sys.modules["telegram"] = telegram_stub

    telegram_ext_stub = types.ModuleType("telegram.ext")

    class Application:
        @classmethod
        def builder(cls):
            return cls()

        def token(self, _):
            return self

        def build(self):
            return self

        def add_handler(self, _):
            return None

        def run_polling(self, **_):
            return None

    class CommandHandler:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class CallbackQueryHandler(CommandHandler):
        pass

    class ContextTypes:
        DEFAULT_TYPE = object

    telegram_ext_stub.Application = Application
    telegram_ext_stub.CommandHandler = CommandHandler
    telegram_ext_stub.CallbackQueryHandler = CallbackQueryHandler
    telegram_ext_stub.ContextTypes = ContextTypes
    sys.modules["telegram.ext"] = telegram_ext_stub

    import bot

from game_logic import GameManager


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append({"text": text, "reply_markup": reply_markup})


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})


class BotHandlersTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.game_manager = GameManager()

    def _make_update_and_context(self, user_id, username="user", args=None):
        msg = FakeMessage()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id, username=username, first_name=username),
            message=msg,
        )
        fake_bot = FakeBot()
        context = SimpleNamespace(
            args=args or [],
            application=SimpleNamespace(bot=fake_bot),
        )
        return update, context, msg, fake_bot

    async def test_setname_without_args_returns_error(self):
        update, context, msg, _ = self._make_update_and_context(1, args=[])
        await bot.setname(update, context)
        self.assertIn("Укажите имя", msg.replies[0]["text"])

    async def test_setname_updates_player_display_name(self):
        lobby_id = bot.game_manager.create_lobby(999, "org")
        lobby = bot.game_manager.get_lobby(lobby_id)
        lobby.add_player(1, "alice")

        update, context, msg, _ = self._make_update_and_context(1, username="alice", args=["Агент", "А"])
        await bot.setname(update, context)

        self.assertEqual(lobby.get_player(1).display_name, "Агент А")
        self.assertIn("изменено", msg.replies[0]["text"])

    async def test_addplace_adds_workplace_and_broadcasts(self):
        lobby_id = bot.game_manager.create_lobby(999, "org")
        lobby = bot.game_manager.get_lobby(lobby_id)
        lobby.add_player(1, "alice")
        lobby.add_player(2, "bob")

        update, context, msg, fake_bot = self._make_update_and_context(1, username="alice", args=["Коворкинг"])
        await bot.addplace(update, context)

        self.assertIn("Коворкинг", lobby.custom_workplaces)
        self.assertIn("добавлено", msg.replies[0]["text"])
        self.assertEqual(len(fake_bot.sent), 2)
        self.assertTrue(all("Коворкинг" in item["text"] for item in fake_bot.sent))

    async def test_join_without_lobby_id(self):
        update, context, msg, _ = self._make_update_and_context(1, args=[])
        await bot.join(update, context)
        self.assertIn("Укажите ID лобби", msg.replies[0]["text"])


if __name__ == "__main__":
    unittest.main()
