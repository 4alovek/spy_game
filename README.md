# Spy Game

Игра "Шпион" с лобби, ролями, остановкой игры и голосованием. Telegram-бот и
веб-приложение работают в одном runtime и могут участвовать в одном лобби.

## Структура

- `game/` — чистая игровая логика (`game_logic.py`, `workplaces.py`), без I/O.
- `adapters/telegram/bot.py` — Telegram-бот.
- `adapters/web/` — веб-адаптер на FastAPI + WebSocket (`app.py`, `ws_manager.py`, `protocol.py`).
- `application/` — общий `GameCoordinator`, события и канонические ID игроков.
- `adapters/runtime.py` — единая точка запуска FastAPI и Telegram polling.
- `frontend/` — веб-клиент на vanilla JS.
- `alembic/` — миграции схемы для SQLite/PostgreSQL.
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

Без токена приложение запускается в web-only режиме; кроссплатформенная игра
тогда недоступна.

## Запуск

### Единый runtime

Запуск в текущей консоли поднимает веб-сервер и, при заданном токене, Telegram
polling в одном процессе:

```bash
make run
```

Запуск в фоне:

```bash
make run-bg
```

Режим разработки с reload:

```bash
make run-web        # http://127.0.0.1:8000
```

Лобби создаётся и в браузере, и командой `/create` в Telegram. Код лобби можно
передать пользователям второй платформы; минимум 3 игрока для старта.

`make run-bot` оставлен только для отладки Telegram-интерфейса: он не разделяет
лобби с веб-приложением.

### Docker / VPS

```bash
cp .env.example .env
# заполните TELEGRAM_BOT_TOKEN и POSTGRES_PASSWORD в .env
docker compose up -d --build
```

Compose запускает контейнер приложения и PostgreSQL с постоянным volume,
применяя Alembic-миграции перед стартом приложения. Игра будет доступна на
порту `8000`. HTTPS пока не включён: голосовой WebRTC-чат в таком развёртывании
отключён браузером и потребует reverse proxy с TLS.

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

## Переопределение entrypoint

По умолчанию `Makefile` запускает `adapters.runtime:app`. Для альтернативного
ASGI entrypoint:

```bash
make run APP_MODULE=adapters.runtime:app
```
