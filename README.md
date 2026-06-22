# Spy Game

Игра "Шпион" с лобби, ролями, остановкой игры и голосованием. Доступна в двух
видах поверх общей логики: Telegram-бот и веб-приложение.

## Структура

- `game/` — чистая игровая логика (`game_logic.py`, `workplaces.py`), без I/O.
- `adapters/telegram/bot.py` — Telegram-бот.
- `adapters/web/` — веб-адаптер на FastAPI + WebSocket (`app.py`, `ws_manager.py`, `protocol.py`).
- `frontend/` — веб-клиент на vanilla JS.
- `Makefile` — команды запуска и обслуживания.
- `requirements.txt` — зависимости Python.
- `docs/web-app-plan.md` — план развития веб-версии.

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

### Telegram-бот

Запуск в текущей консоли:

```bash
make run
```

Запуск в фоне:

```bash
make run-bg
```

### Веб-приложение

```bash
make run-web        # http://127.0.0.1:8000
```

Откройте адрес в нескольких вкладках/устройствах: создайте лобби, поделитесь
4-значным кодом, остальные входят по нему. Минимум 3 игрока для старта.

## Тесты

```bash
make test           # или: python -m unittest discover -s tests
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

## Переопределение модуля бота

По умолчанию `Makefile` запускает модуль `adapters.telegram.bot`.
Чтобы запустить другой:

```bash
make run BOT_MODULE=adapters.telegram.bot
```
