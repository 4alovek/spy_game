import os
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from game.game_logic import GameManager, GameResult, Lobby

# Инициализация менеджера игр
game_manager = GameManager()


async def broadcast_to_lobby(bot: Bot, lobby: Lobby, message: str):
    """Отправить сообщение всем игрокам в лобби"""
    for player in lobby.players:
        try:
            await bot.send_message(chat_id=player.user_id, text=message)
        except Exception as e:
            print(f"Не удалось отправить сообщение игроку {player.display_name}: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🕵️ Добро пожаловать в игру 'Шпион'!\n\n"
        "📋 Команды:\n"
        "/help - Посмотреть справку\n"        
        "/create - Создать лобби (для организатора)\n"
        "/join <ID> - Присоединиться к лобби\n"
        "/setname <имя> - Установить игровое имя\n"
        "/addplace <место> - Добавить своё место работы\n"
        "/places - Показать все места работы\n"
        "/leave - Покинуть лобби\n"
        "/players - Список игроков в лобби\n"
        "/startgame - Начать игру (только организатор)\n"
        "/role - Узнать свою роль\n"
        "/stopgame - Остановить игру и сделать ход\n"
        "/win <workers/spy> - Объявить победителя (только организатор)\n"
        "/endgame - Завершить текущую игру (только организатор)\n"
        "/closelobby - Закрыть лобби (только организатор)"
    )


async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать новое лобби"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    lobby_id = game_manager.create_lobby(user_id, username)
    
    await update.message.reply_text(
        f"✅ Лобби создано!\n\n"
        f"🆔 ID лобби: {lobby_id}\n"
        f"👤 Организатор: {username}\n\n"
        f"Игроки могут присоединиться командой:\n"
        f"/join {lobby_id}"
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Присоединиться к лобби"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Укажите ID лобби: /join <ID>")
        return
    
    lobby_id = context.args[0]
    lobby = game_manager.get_lobby(lobby_id)
    
    if not lobby:
        await update.message.reply_text(f"❌ Лобби {lobby_id} не найдено")
        return
    
    if lobby.add_player(user_id, username):
        await update.message.reply_text(
            f"✅ Вы присоединились к лобби {lobby_id}!\n"
            f"👥 Игроков в лобби: {len(lobby.players)}\n\n"
            f"💡 Вы можете установить игровое имя: /setname <имя>"
        )
        
        # Уведомляем всех игроков о новом участнике
        player = lobby.get_player(user_id)
        await broadcast_to_lobby(
            context.application.bot,
            lobby,
            f"➕ {player.display_name} присоединился к игре!\n👥 Игроков: {len(lobby.players)}"
        )
    else:
        if lobby.game_started:
            await update.message.reply_text("❌ Игра уже началась, нельзя присоединиться")
        else:
            await update.message.reply_text("❌ Вы уже в этом лобби")


async def leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покинуть лобби"""
    user_id = update.effective_user.id
    
    # Находим лобби, в котором находится игрок
    user_lobby = None
    for lobby in game_manager.lobbies.values():
        if any(p.user_id == user_id for p in lobby.players):
            user_lobby = lobby
            break
    
    if not user_lobby:
        await update.message.reply_text("❌ Вы не находитесь ни в одном лобби")
        return
    
    # Сохраняем имя до удаления
    player = user_lobby.get_player(user_id)
    player_name = player.display_name if player else "Игрок"
    
    if user_lobby.remove_player(user_id):
        await update.message.reply_text(f"✅ Вы покинули лобби {user_lobby.lobby_id}")
        
        # Уведомляем остальных игроков
        await broadcast_to_lobby(
            context.application.bot,
            user_lobby,
            f"➖ {player_name} покинул игру\n👥 Игроков: {len(user_lobby.players)}"
        )
    else:
        await update.message.reply_text("❌ Нельзя покинуть лобби во время игры")


async def players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список игроков"""
    user_id = update.effective_user.id
    
    # Находим лобби игрока
    user_lobby = None
    for lobby in game_manager.lobbies.values():
        if any(p.user_id == user_id for p in lobby.players) or lobby.is_organizer(user_id):
            user_lobby = lobby
            break
    
    if not user_lobby:
        await update.message.reply_text("❌ Вы не находитесь ни в одном лобби")
        return
    
    players_list = user_lobby.get_players_list()
    status = "🎮 Игра идёт" if user_lobby.game_started else "⏳ Ожидание"
    
    message = f"🆔 Лобби: {user_lobby.lobby_id}\n"
    message += f"📊 Статус: {status}\n"
    message += f"👤 Организатор: {user_lobby.organizer_username}\n"
    message += f"👥 Игроков: {len(players_list)}\n\n"
    message += "Список игроков:\n"
    for i, player in enumerate(players_list, 1):
        message += f"{i}. {player}\n"
    
    await update.message.reply_text(message)


async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить игровое имя"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Укажите имя: /setname <ваше_имя>")
        return
    
    new_name = " ".join(context.args)
    
    if len(new_name) > 30:
        await update.message.reply_text("❌ Имя слишком длинное (максимум 30 символов)")
        return
    
    # Находим лобби игрока
    user_lobby = None
    for lobby in game_manager.lobbies.values():
        if any(p.user_id == user_id for p in lobby.players):
            user_lobby = lobby
            break
    
    if not user_lobby:
        await update.message.reply_text("❌ Сначала присоединитесь к лобби через /join <ID>")
        return
    
    if user_lobby.set_player_name(user_id, new_name):
        await update.message.reply_text(f"✅ Ваше игровое имя изменено на: {new_name}")
    else:
        await update.message.reply_text("❌ Нельзя изменить имя во время игры")


async def addplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить кастомное место работы"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Укажите место работы: /addplace <место>")
        return
    
    workplace = " ".join(context.args)
    
    if len(workplace) > 50:
        await update.message.reply_text("❌ Название слишком длинное (максимум 50 символов)")
        return
    
    # Находим лобби игрока
    user_lobby = None
    for lobby in game_manager.lobbies.values():
        if any(p.user_id == user_id for p in lobby.players) or lobby.is_organizer(user_id):
            user_lobby = lobby
            break
    
    if not user_lobby:
        await update.message.reply_text("❌ Сначала присоединитесь к лобби")
        return
    
    if user_lobby.add_custom_workplace(workplace):
        await update.message.reply_text(f"✅ Место работы '{workplace}' добавлено!")
        
        # Уведомляем всех
        await broadcast_to_lobby(
            context.application.bot,
            user_lobby,
            f"➕ Добавлено новое место: {workplace}"
        )
    else:
        if user_lobby.game_started:
            await update.message.reply_text("❌ Нельзя добавлять места во время игры")
        else:
            await update.message.reply_text("❌ Это место уже есть в списке")


async def places(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все места работы"""
    user_id = update.effective_user.id
    
    # Находим лобби игрока
    user_lobby = None
    for lobby in game_manager.lobbies.values():
        if any(p.user_id == user_id for p in lobby.players) or lobby.is_organizer(user_id):
            user_lobby = lobby
            break
    
    if not user_lobby:
        await update.message.reply_text("❌ Сначала присоединитесь к лобби")
        return
    
    all_places = user_lobby.get_all_workplaces()
    custom_count = len(user_lobby.custom_workplaces)
    
    message = f"📍 Всего мест работы: {len(all_places)}\n"
    if custom_count > 0:
        message += f"✨ Добавлено участниками: {custom_count}\n"
    message += "\n"
    
    for i, place in enumerate(all_places, 1):
        custom_mark = " ✨" if place in user_lobby.custom_workplaces else ""
        message += f"{i}. {place}{custom_mark}\n"
        
        # Разбиваем на несколько сообщений если слишком длинное
        if len(message) > 3500:
            await update.message.reply_text(message)
            message = ""
    
    if message:
        await update.message.reply_text(message)


async def startgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать игру (только организатор)"""
    user_id = update.effective_user.id
    
    # Находим лобби организатора
    organizer_lobby = None
    for lobby in game_manager.lobbies.values():
        if lobby.is_organizer(user_id):
            organizer_lobby = lobby
            break
    
    if not organizer_lobby:
        await update.message.reply_text("❌ У вас нет лобби для управления")
        return
    
    if organizer_lobby.start_game():
        # Сообщение для организатора с подсказкой
        await update.message.reply_text(
            f"🎮 Игра началась!\n\n"
            f"👥 Игроков: {len(organizer_lobby.players)}\n"
            f"🕵️ Шпион: 1\n"
            f"👷 Работники: {len(organizer_lobby.players) - 1}\n\n"
            f"💡 Подсказки:\n"
            f"• Игроки узнают роли через /role\n"
            f"• Игроки сами останавливают игру через кнопки\n"
            f"• Или вы можете объявить: /win workers или /win spy"
        )
        
        # Общее сообщение всем игрокам
        await broadcast_to_lobby(
            context.application.bot,
            organizer_lobby,
            f"🎮 Игра началась!\n\n"
            f"👥 Игроков: {len(organizer_lobby.players)}\n"
            f"🕵️ Шпион: 1\n"
            f"👷 Работники: {len(organizer_lobby.players) - 1}\n\n"
            f"Узнайте свою роль командой /role"
        )
    else:
        if organizer_lobby.game_started:
            await update.message.reply_text("❌ Игра уже началась")
        else:
            await update.message.reply_text("❌ Недостаточно игроков (минимум 3)")


async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Узнать свою роль"""
    user_id = update.effective_user.id
    
    # Находим лобби игрока
    user_lobby = None
    for lobby in game_manager.lobbies.values():
        if any(p.user_id == user_id for p in lobby.players):
            user_lobby = lobby
            break
    
    if not user_lobby:
        await update.message.reply_text("❌ Вы не находитесь ни в одном лобби")
        return
    
    role_info = user_lobby.get_player_role_info(user_id)
    
    if not role_info:
        await update.message.reply_text("❌ Игра ещё не началась. Ждите команды /startgame от организатора")
        return
    
    # Создаём кнопку для остановки игры (если игра не остановлена)
    keyboard = None
    if not user_lobby.game_stopped:
        keyboard = [[InlineKeyboardButton("⏸️ Остановить игру", callback_data=f"stop_{user_lobby.lobby_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
    else:
        reply_markup = None
    
    if role_info["is_spy"]:
        message = "🕵️ Вы - ШПИОН!\n\n"
        message += f"👥 Всего игроков: {role_info['player_count']}\n"
        message += "🎯 Ваша цель: узнать место работы других игроков\n\n"
        message += "⚠️ Вы НЕ знаете, где работают остальные!"
        if not user_lobby.game_stopped:
            message += "\n\n💡 Когда будете готовы угадать место - нажмите кнопку ниже"
    else:
        message = "👷 Вы - РАБОТНИК!\n\n"
        message += f"🏢 Место работы: {role_info['workplace']}\n"
        message += f"👥 Всего игроков: {role_info['player_count']}\n"
        message += "🎯 Ваша цель: найти шпиона среди коллег"
        if not user_lobby.game_stopped:
            message += "\n\n💡 Когда найдёте шпиона - нажмите кнопку ниже"
    
    await update.message.reply_text(message, reply_markup=reply_markup)


async def stopgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Остановить игру - показать кнопку"""
    user_id = update.effective_user.id
    
    # Находим лобби игрока
    user_lobby = None
    for lobby in game_manager.lobbies.values():
        if any(p.user_id == user_id for p in lobby.players):
            user_lobby = lobby
            break
    
    if not user_lobby:
        await update.message.reply_text("❌ Вы не находитесь ни в одном лобби")
        return
    
    if not user_lobby.game_started:
        await update.message.reply_text("❌ Игра ещё не началась")
        return
    
    if user_lobby.game_stopped:
        await update.message.reply_text("❌ Игра уже остановлена")
        return
    
    player = user_lobby.get_player(user_id)
    if not player:
        return
    
    keyboard = [[InlineKeyboardButton("⏸️ Остановить игру", callback_data=f"stop_{user_lobby.lobby_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Нажмите кнопку для остановки игры:", reply_markup=reply_markup)


async def show_player_selection(query, lobby: Lobby, user_id: int, bot: Bot):
    """Показать кнопки выбора игрока для обвинения"""
    buttons = []
    for player in lobby.players:
        if player.user_id != user_id:  # Нельзя обвинить себя
            buttons.append([InlineKeyboardButton(
                player.display_name, 
                callback_data=f"accuse_{lobby.lobby_id}_{player.user_id}"
            )])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(
        "⏸️ Вы остановили игру!\n\n"
        "Выберите игрока, которого вы обвиняете в шпионаже:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("stop_"):
        # Остановка игры
        lobby_id = data.split("_")[1]
        lobby = game_manager.get_lobby(lobby_id)
        
        if not lobby or not lobby.game_started or lobby.game_stopped:
            await query.edit_message_text("❌ Игра уже остановлена или завершена")
            return
        
        player = lobby.get_player(user_id)
        if not player:
            await query.edit_message_text("❌ Вы не участвуете в этой игре")
            return
        
        if player.is_spy:
            # Шпион остановил игру
            if lobby.stop_game_by_spy(user_id):
                await query.edit_message_text(
                    "⏸️ Вы остановили игру!\n\n"
                    "Теперь введите команду:\n"
                    "/guess <место работы>\n\n"
                    "Например: /guess Банк"
                )
                
                # Уведомляем всех
                await broadcast_to_lobby(
                    context.application.bot,
                    lobby,
                    f"⏸️ {player.display_name} остановил игру!\n\n"
                    f"Шпион указывает место работы..."
                )
        else:
            # Работник остановил игру - выбор игрока
            await show_player_selection(query, lobby, user_id, context.application.bot)
    
    elif data.startswith("accuse_"):
        # Обвинение игрока
        parts = data.split("_")
        lobby_id = parts[1]
        accused_id = int(parts[2])
        
        lobby = game_manager.get_lobby(lobby_id)
        if not lobby:
            await query.edit_message_text("❌ Лобби не найдено")
            return
        
        result = lobby.stop_game_by_worker(user_id, accused_id)
        
        player = lobby.get_player(user_id)
        accused = lobby.get_player(accused_id)
        
        if result:
            await query.edit_message_text(
                f"⏸️ Вы обвинили {accused.display_name}!\n\n"
                f"Ожидайте результата..."
            )
            
            # Уведомляем всех
            message = f"⏸️ {player.display_name} остановил игру!\n\n"
            message += f"👉 Обвинён: {accused.display_name}\n\n"
            
            if result == "workers_win":
                message += f"✅ {accused.display_name} действительно был шпионом!\n\n"
                message += f"🎉 ПОБЕДА РАБОТНИКОВ!\n"
                message += f"🏢 Место работы было: {lobby.current_workplace}"
            else:
                message += f"❌ {accused.display_name} оказался работником!\n"
                message += f"🕵️ Настоящий шпион: {lobby.spy.display_name}\n\n"
                message += f"🎉 ПОБЕДА ШПИОНА!\n"
                message += f"🏢 Место работы было: {lobby.current_workplace}"
            
            await broadcast_to_lobby(context.application.bot, lobby, message)
        else:
            await query.edit_message_text("❌ Не удалось обвинить игрока")
    
    elif data.startswith("vote_"):
        # Голосование за догадку шпиона
        parts = data.split("_")
        lobby_id = parts[1]
        vote = parts[2] == "yes"
        
        lobby = game_manager.get_lobby(lobby_id)
        if not lobby:
            await query.edit_message_text("❌ Лобби не найдено")
            return
        
        player = lobby.get_player(user_id)
        if not player:
            await query.edit_message_text("❌ Вы не участвуете в этой игре")
            return
        
        if lobby.vote(user_id, vote):
            vote_text = "Да ✅" if vote else "Нет ❌"
            await query.edit_message_text(f"Ваш голос: {vote_text}")
            
            # Проверяем, все ли проголосовали
            result = lobby.get_vote_result()
            if result:
                # Все проголосовали, объявляем результат
                workers_count = len(lobby.get_workers())
                yes_votes = sum(1 for v in lobby.votes.values() if v)
                no_votes = workers_count - yes_votes
                
                message = f"📊 Голосование завершено!\n\n"
                message += f"За: {yes_votes}\n"
                message += f"Против: {no_votes}\n\n"
                
                if result == "spy_win":
                    message += f"🎉 ПОБЕДА ШПИОНА!\n\n"
                    message += f"🕵️ Шпион: {lobby.spy.display_name}\n"
                    message += f"✅ Угадал место: {lobby.guessed_workplace}\n"
                    message += f"🏢 Настоящее место: {lobby.current_workplace}"
                else:
                    message += f"🎉 ПОБЕДА РАБОТНИКОВ!\n\n"
                    message += f"🕵️ Шпион: {lobby.spy.display_name}\n"
                    message += f"❌ Неправильная догадка: {lobby.guessed_workplace}\n"
                    message += f"🏢 Настоящее место: {lobby.current_workplace}"
                
                await broadcast_to_lobby(context.application.bot, lobby, message)
        else:
            await query.edit_message_text("❌ Не удалось проголосовать")


async def guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шпион угадывает место работы"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Укажите место работы: /guess <место>")
        return
    
    guessed_place = " ".join(context.args)
    
    # Находим лобби игрока
    user_lobby = None
    for lobby in game_manager.lobbies.values():
        if any(p.user_id == user_id for p in lobby.players):
            user_lobby = lobby
            break
    
    if not user_lobby:
        await update.message.reply_text("❌ Вы не находитесь ни в одном лобби")
        return
    
    if not user_lobby.game_stopped:
        await update.message.reply_text("❌ Сначала остановите игру")
        return
    
    player = user_lobby.get_player(user_id)
    if not player or not player.is_spy:
        await update.message.reply_text("❌ Только шпион может угадывать место работы")
        return
    
    if user_lobby.set_spy_guess(guessed_place):
        await update.message.reply_text(
            f"✅ Ваша догадка: {guessed_place}\n\n"
            f"Ожидайте голосования работников..."
        )
        
        # Запускаем голосование у работников
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f"vote_{user_lobby.lobby_id}_yes"),
                InlineKeyboardButton("❌ Нет", callback_data=f"vote_{user_lobby.lobby_id}_no")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        workers = user_lobby.get_workers()
        message = f"🗳️ ГОЛОСОВАНИЕ\n\n"
        message += f"🕵️ Шпион {player.display_name} угадал место:\n"
        message += f"📍 {guessed_place}\n\n"
        message += f"Согласны ли вы с этим ответом?\n"
        message += f"(Для победы шпиона нужно больше половины голосов 'Да')"
        
        for worker in workers:
            try:
                await context.application.bot.send_message(
                    chat_id=worker.user_id,
                    text=message,
                    reply_markup=reply_markup
                )
            except Exception as e:
                print(f"Не удалось отправить сообщение работнику {worker.display_name}: {e}")
    else:
        await update.message.reply_text("❌ Не удалось установить догадку")


async def win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Объявить победителя (только организатор)"""
    user_id = update.effective_user.id
    
    # Находим лобби организатора
    organizer_lobby = None
    for lobby in game_manager.lobbies.values():
        if lobby.is_organizer(user_id):
            organizer_lobby = lobby
            break
    
    if not organizer_lobby:
        await update.message.reply_text("❌ У вас нет лобби для управления")
        return
    
    if not organizer_lobby.game_started:
        await update.message.reply_text("❌ Игра не начата")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("❌ Укажите победителя: /win workers или /win spy")
        return
    
    winner = context.args[0].lower()
    
    if winner == "workers":
        spy_name = organizer_lobby.spy.display_name if organizer_lobby.spy else "Неизвестно"
        workplace = organizer_lobby.current_workplace
        
        # Сообщение для организатора с подсказкой
        await update.message.reply_text(
            f"🎉 ПОБЕДА РАБОТНИКОВ!\n\n"
            f"🕵️ Шпионом был: {spy_name}\n"
            f"🏢 Место работы было: {workplace}\n\n"
            f"💡 Начните новый раунд: /startgame"
        )
        
        # Общее сообщение всем игрокам
        message = f"🎉 ПОБЕДА РАБОТНИКОВ!\n\n"
        message += f"🕵️ Шпионом был: {spy_name}\n"
        message += f"🏢 Место работы было: {workplace}"
        
        organizer_lobby.end_game(GameResult.WORKERS_WIN)
        await broadcast_to_lobby(context.application.bot, organizer_lobby, message)
        
    elif winner == "spy":
        spy_name = organizer_lobby.spy.display_name if organizer_lobby.spy else "Неизвестно"
        workplace = organizer_lobby.current_workplace
        
        # Сообщение для организатора с подсказкой
        await update.message.reply_text(
            f"🎉 ПОБЕДА ШПИОНА!\n\n"
            f"🕵️ Шпион: {spy_name}\n"
            f"🏢 Место работы было: {workplace}\n\n"
            f"💡 Начните новый раунд: /startgame"
        )
        
        # Общее сообщение всем игрокам
        message = f"🎉 ПОБЕДА ШПИОНА!\n\n"
        message += f"🕵️ Шпион: {spy_name}\n"
        message += f"🏢 Место работы было: {workplace}"
        
        organizer_lobby.end_game(GameResult.SPY_WIN)
        await broadcast_to_lobby(context.application.bot, organizer_lobby, message)
        
    else:
        await update.message.reply_text("❌ Неверный параметр. Используйте: /win workers или /win spy")


async def endgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершить игру без определения победителя"""
    user_id = update.effective_user.id
    
    # Находим лобби организатора
    organizer_lobby = None
    for lobby in game_manager.lobbies.values():
        if lobby.is_organizer(user_id):
            organizer_lobby = lobby
            break
    
    if not organizer_lobby:
        await update.message.reply_text("❌ У вас нет лобби для управления")
        return
    
    if not organizer_lobby.game_started:
        await update.message.reply_text("❌ Игра не начата")
        return
    
    spy_name = organizer_lobby.spy.display_name if organizer_lobby.spy else "Неизвестно"
    workplace = organizer_lobby.current_workplace
    
    organizer_lobby.end_game(GameResult.WORKERS_WIN)  # Технически завершаем игру
    
    # Сообщение для организатора с подсказкой
    await update.message.reply_text(
        f"⏹️ Игра завершена\n\n"
        f"🕵️ Шпионом был: {spy_name}\n"
        f"🏢 Место работы было: {workplace}\n\n"
        f"💡 Начните новый раунд: /startgame"
    )
    
    # Общее сообщение всем игрокам
    await broadcast_to_lobby(
        context.application.bot,
        organizer_lobby,
        f"⏹️ Игра завершена\n\n"
        f"🕵️ Шпионом был: {spy_name}\n"
        f"🏢 Место работы было: {workplace}"
    )


async def closelobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть лобби (только организатор)"""
    user_id = update.effective_user.id
    
    # Находим лобби организатора
    organizer_lobby = None
    lobby_id_to_delete = None
    for lobby_id, lobby in game_manager.lobbies.items():
        if lobby.is_organizer(user_id):
            organizer_lobby = lobby
            lobby_id_to_delete = lobby_id
            break
    
    if not organizer_lobby:
        await update.message.reply_text("❌ У вас нет лобби для управления")
        return
    
    game_manager.delete_lobby(lobby_id_to_delete)
    await update.message.reply_text(f"✅ Лобби {lobby_id_to_delete} закрыто")


def main():
    """Запуск бота"""
    # Получаем токен из переменной окружения
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    if not TOKEN:
        print("❌ Ошибка: не установлена переменная окружения TELEGRAM_BOT_TOKEN")
        print("Установите токен командой: export TELEGRAM_BOT_TOKEN='ваш_токен'")
        return
    
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("create", create))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("setname", setname))
    application.add_handler(CommandHandler("addplace", addplace))
    application.add_handler(CommandHandler("places", places))
    application.add_handler(CommandHandler("leave", leave))
    application.add_handler(CommandHandler("players", players))
    application.add_handler(CommandHandler("startgame", startgame))
    application.add_handler(CommandHandler("role", role))
    application.add_handler(CommandHandler("stopgame", stopgame))
    application.add_handler(CommandHandler("guess", guess))
    application.add_handler(CommandHandler("win", win))
    application.add_handler(CommandHandler("endgame", endgame))
    application.add_handler(CommandHandler("closelobby", closelobby))
    
    # Регистрируем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    print("🤖 Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
