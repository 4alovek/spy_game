"""Telegram-клиент общего GameCoordinator.

Команды остаются тонким UI над теми же действиями, что получает WebSocket.
"""
import os
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from application.coordinator import GameCoordinator, GameEvent
from application.identity import telegram_user_id
from game.game_logic import Lobby


coordinator = GameCoordinator()
game_manager = coordinator.game_manager  # сохранено для совместимости с тестами/отладки


def configure(shared_coordinator: GameCoordinator) -> None:
    """Подключить бот к runtime веб-приложения до регистрации обработчиков."""
    global coordinator, game_manager
    coordinator = shared_coordinator
    game_manager = coordinator.game_manager


def _coordinator() -> GameCoordinator:
    # Старые тесты заменяли bot.game_manager напрямую.
    if coordinator.game_manager is not game_manager:
        coordinator.reset(game_manager)
    return coordinator


def _user(update: Update) -> tuple[str, str]:
    raw = update.effective_user
    return telegram_user_id(raw.id), (raw.username or raw.first_name or "Игрок")


def _player_lobby(user_id: str) -> Optional[Lobby]:
    for lobby in game_manager.lobbies.values():
        if lobby.get_player(user_id):
            return lobby
    return None


def _host_lobby(user_id: str) -> Optional[Lobby]:
    return next((lobby for lobby in game_manager.lobbies.values() if lobby.is_organizer(user_id)), None)


async def broadcast_to_lobby(bot: Bot, lobby: Lobby, message: str, reply_markup=None) -> None:
    for player in lobby.players:
        if not player.user_id.startswith("tg:"):
            continue
        try:
            await bot.send_message(chat_id=int(player.user_id.removeprefix("tg:")), text=message,
                                   reply_markup=reply_markup)
        except Exception as exc:
            print(f"Не удалось отправить сообщение игроку {player.display_name}: {exc}")


def install_notifier(application: Application, shared_coordinator: GameCoordinator) -> None:
    """Подписать Telegram-проекцию на события, включая действия веб-игроков."""
    async def notify(event: GameEvent) -> None:
        lobby = shared_coordinator.get_lobby(event.lobby_id)
        if not lobby:
            return
        actor = lobby.get_player(event.actor_id) if event.actor_id else None
        actor_name = actor.display_name if actor else "Игрок"
        if event.kind == "lobby_changed":
            change = event.data.get("change")
            if change == "joined":
                await broadcast_to_lobby(application.bot, lobby,
                                         f"➕ {event.data.get('name', actor_name)} присоединился к игре!")
            elif change in ("left", "expired"):
                name = event.data.get("name", actor_name)
                await broadcast_to_lobby(application.bot, lobby, f"➖ {name} покинул игру")
        elif event.kind == "round_started":
            await broadcast_to_lobby(application.bot, lobby,
                f"🎮 Игра началась! Игроков: {len(lobby.players)}\nУзнайте свою роль: /role")
        elif event.kind == "spy_stopped":
            await broadcast_to_lobby(application.bot, lobby,
                f"⏸️ {actor_name} остановил игру и называет место работы…")
        elif event.kind == "voting_started":
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Да", callback_data=f"vote_{lobby.lobby_id}_yes"),
                InlineKeyboardButton("❌ Нет", callback_data=f"vote_{lobby.lobby_id}_no"),
            ]])
            text = (f"🗳️ Шпион {actor_name} назвал место: {event.data.get('guess')}\n"
                    "Согласны ли вы с ответом?")
            for worker in lobby.get_workers():
                if worker.user_id.startswith("tg:"):
                    try:
                        await application.bot.send_message(
                            chat_id=int(worker.user_id.removeprefix("tg:")), text=text, reply_markup=markup)
                    except Exception as exc:
                        print(f"Не удалось начать голосование: {exc}")
        elif event.kind == "round_finished":
            result = event.data["result"]
            winner = "ШПИОНА" if result["winner"] == "spy" else "РАБОТНИКОВ"
            message = (f"🎉 ПОБЕДА {winner}!\n\n🕵️ Шпион: {result['spy_name']}\n"
                       f"🏢 Место работы: {result['workplace']}")
            if result.get("guessed_workplace"):
                message += f"\n💭 Догадка: {result['guessed_workplace']}"
            if result.get("accused_name"):
                message += f"\n👉 Обвинён: {result['accused_name']}"
            await broadcast_to_lobby(application.bot, lobby, message)
        elif event.kind == "round_cancelled":
            await broadcast_to_lobby(application.bot, lobby, "⏹️ Раунд завершён организатором")

    shared_coordinator.subscribe(notify)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕵️ Игра «Шпион»\n\n"
        "/create — создать лобби\n/join <ID> — войти\n/role — узнать роль\n"
        "/players — игроки\n/startgame — начать игру\n/stopgame — сделать ход\n"
        "/guess <место> — догадка шпиона\n/leave — выйти")


async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, name = _user(update)
    lobby_id = await _coordinator().create_lobby(user_id, name, "telegram", source="telegram")
    await update.message.reply_text(
        f"✅ Лобби {lobby_id} создано, вы уже в нём.\n"
        f"Игроки из Telegram: /join {lobby_id}\n"
        f"Игроки из веба могут ввести этот код на главной странице.")


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, name = _user(update)
    if not context.args:
        await update.message.reply_text("❌ Укажите ID лобби: /join <ID>")
        return
    result = await _coordinator().join_lobby(context.args[0], user_id, name, "telegram", source="telegram")
    await update.message.reply_text(
        f"✅ Вы присоединились к лобби {context.args[0]}" if result.ok else f"❌ {result.error}")


async def leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _player_lobby(user_id)
    if not lobby:
        await update.message.reply_text("❌ Вы не находитесь в лобби")
        return
    result = await _coordinator().leave_lobby(lobby.lobby_id, user_id, source="telegram")
    await update.message.reply_text("✅ Вы покинули лобби" if result.ok else f"❌ {result.error}")


async def players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _player_lobby(user_id) or _host_lobby(user_id)
    if not lobby:
        await update.message.reply_text("❌ Вы не находитесь в лобби")
        return
    names = "\n".join(f"{i}. {p.display_name}" for i, p in enumerate(lobby.players, 1))
    await update.message.reply_text(f"🆔 Лобби {lobby.lobby_id}\n👥 Игроки:\n{names}")


async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _player_lobby(user_id)
    if not context.args or not lobby:
        await update.message.reply_text("❌ Укажите имя после /setname и войдите в лобби")
        return
    result = await _coordinator().act(lobby.lobby_id, user_id, "set_name",
                                      source="telegram", name=" ".join(context.args))
    await update.message.reply_text("✅ Имя изменено" if result.ok else f"❌ {result.error}")


async def addplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _player_lobby(user_id) or _host_lobby(user_id)
    if not context.args or not lobby:
        await update.message.reply_text("❌ Укажите место после /addplace")
        return
    result = await _coordinator().act(lobby.lobby_id, user_id, "add_place",
                                      source="telegram", place=" ".join(context.args))
    await update.message.reply_text("✅ Место добавлено" if result.ok else f"❌ {result.error}")


async def places(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _player_lobby(user_id) or _host_lobby(user_id)
    if not lobby:
        await update.message.reply_text("❌ Сначала войдите в лобби")
        return
    await update.message.reply_text("📍 Места работы:\n" + "\n".join(lobby.get_all_workplaces()))


async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _host_lobby(user_id)
    if not lobby:
        await update.message.reply_text("❌ У вас нет лобби для управления")
        return
    result = await _coordinator().act(lobby.lobby_id, user_id, "start", source="telegram")
    await update.message.reply_text("✅ Игра началась" if result.ok else f"❌ {result.error}")


async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _player_lobby(user_id)
    info = lobby.get_player_role_info(user_id) if lobby else None
    if not info:
        await update.message.reply_text("❌ Игра ещё не началась")
        return
    text = "🕵️ Вы — ШПИОН" if info["is_spy"] else f"👷 Вы — РАБОТНИК\n🏢 {info['workplace']}"
    markup = None if lobby.game_stopped else InlineKeyboardMarkup([[
        InlineKeyboardButton("⏸️ Остановить игру", callback_data=f"stop_{lobby.lobby_id}")]])
    await update.message.reply_text(text, reply_markup=markup)


async def stopgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _player_lobby(user_id)
    if not lobby or not lobby.game_started or lobby.game_stopped:
        await update.message.reply_text("❌ Сейчас нельзя остановить игру")
        return
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("⏸️ Остановить игру", callback_data=f"stop_{lobby.lobby_id}")]])
    await update.message.reply_text("Нажмите кнопку для остановки игры", reply_markup=markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = telegram_user_id(query.from_user.id)
    parts = query.data.split("_")
    action, lobby_id = parts[0], parts[1]
    lobby = _coordinator().get_lobby(lobby_id)
    if not lobby:
        await query.edit_message_text("❌ Лобби не найдено")
        return
    if action == "stop":
        player = lobby.get_player(user_id)
        if not player:
            await query.edit_message_text("❌ Вы не участвуете в игре")
        elif player.is_spy:
            result = await _coordinator().act(lobby_id, user_id, "stop_spy", source="telegram")
            await query.edit_message_text("Введите /guess <место>" if result.ok else f"❌ {result.error}")
        else:
            buttons = [[InlineKeyboardButton(p.display_name, callback_data=f"accuse_{lobby_id}_{p.user_id}")]
                       for p in lobby.players if p.user_id != user_id]
            await query.edit_message_text("Кого обвиняете?", reply_markup=InlineKeyboardMarkup(buttons))
    elif action == "accuse" and len(parts) == 3:
        result = await _coordinator().act(lobby_id, user_id, "accuse", source="telegram", target_id=parts[2])
        await query.edit_message_text("✅ Обвинение принято" if result.ok else f"❌ {result.error}")
    elif action == "vote" and len(parts) == 3:
        result = await _coordinator().act(lobby_id, user_id, "vote", source="telegram", value=parts[2] == "yes")
        await query.edit_message_text("✅ Голос учтён" if result.ok else f"❌ {result.error}")


async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _player_lobby(user_id)
    if not context.args or not lobby:
        await update.message.reply_text("❌ Укажите место: /guess <место>")
        return
    result = await _coordinator().act(lobby.lobby_id, user_id, "guess", source="telegram",
                                      place=" ".join(context.args))
    await update.message.reply_text("✅ Догадка отправлена на голосование" if result.ok else f"❌ {result.error}")


async def win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _host_lobby(user_id)
    winner = context.args[0].lower() if context.args else ""
    if not lobby:
        await update.message.reply_text("❌ У вас нет лобби для управления")
        return
    result = await _coordinator().act(lobby.lobby_id, user_id, "win", source="telegram", winner=winner)
    await update.message.reply_text("✅ Победитель объявлен" if result.ok else f"❌ {result.error}")


async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _host_lobby(user_id)
    if not lobby:
        await update.message.reply_text("❌ У вас нет лобби для управления")
        return
    result = await _coordinator().act(lobby.lobby_id, user_id, "endgame", source="telegram")
    await update.message.reply_text("✅ Раунд завершён" if result.ok else f"❌ {result.error}")


async def closelobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, _ = _user(update)
    lobby = _host_lobby(user_id)
    if not lobby:
        await update.message.reply_text("❌ У вас нет лобби для управления")
        return
    result = await _coordinator().act(lobby.lobby_id, user_id, "close", source="telegram")
    await update.message.reply_text("✅ Лобби закрыто" if result.ok else f"❌ {result.error}")


def build_application(shared_coordinator: Optional[GameCoordinator] = None) -> Application:
    if shared_coordinator:
        configure(shared_coordinator)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Не установлена переменная TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(token).build()
    for command, handler in (
        ("start", start), ("help", start), ("create", create), ("join", join),
        ("leave", leave), ("players", players), ("setname", setname), ("addplace", addplace),
        ("places", places), ("startgame", startgame), ("role", role), ("stopgame", stopgame),
        ("guess", guess), ("win", win), ("endgame", endgame), ("closelobby", closelobby),
    ):
        application.add_handler(CommandHandler(command, handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    install_notifier(application, coordinator)
    return application


def main():
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
