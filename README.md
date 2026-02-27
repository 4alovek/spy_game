# Spy Game Telegram Bot

Телеграм-бот для игры "Шпион" с лобби, ролями, остановкой игры и голосованием.

## Структура

- `bot.py` - основной бот с обработчиками команд Telegram.
- `game_logic.py` - логика лобби и механики игры.
- `workplaces.py` - базовый список мест работы.
- `Makefile` - команды запуска и обслуживания.
- `requirements.txt` - зависимости Python.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Переменные окружения

```bash
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
```

## Запуск

Запуск в текущей консоли:

```bash
make run
```

Запуск в фоне:

```bash
make run-bg
```

## Управление процессом

Проверить статус:

```bash
make status
```

Посмотреть логи:

```bash
make logs
```

Остановить:

```bash
make stop
```

Перезапустить:

```bash
make restart
```

## Переопределение файла бота

По умолчанию `Makefile` запускает `bot.py`.  
Чтобы запускать другой файл:

```bash
make run BOT_FILE=telegram_bot.py
```
