# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

The party game "Spy" (Шпион): players join a lobby, one is secretly assigned the spy, and the rest share a workplace. The spy tries to guess the workplace; the workers try to identify the spy. Shipped as **two adapters over one shared logic layer**: a Telegram bot and a FastAPI web app.

## Commands

```bash
# Run the test suite
make test           # or: python -m unittest discover -s tests

# Run a single test
python -m unittest tests.test_game_logic.LobbyGameLogicTests.test_start_game_assigns_one_spy_and_workplace_for_workers

# Run the Telegram bot (requires TELEGRAM_BOT_TOKEN in the environment)
make run            # foreground (module: adapters.telegram.bot)
make run-bg         # background (PID in .bot.pid, output to bot.log)
make status / make logs / make stop / make restart

# Run the web app (FastAPI + WebSocket, serves frontend/ at http://127.0.0.1:8000)
make run-web
```

Everything runs from the repo root so the `game` / `adapters` packages resolve (`make run` uses `python -m`). There is no linter or formatter configured.

`bot.py` reads `TELEGRAM_BOT_TOKEN` via `os.getenv` only — there is **no** dotenv loading, so `make run` does not pick up `.env` automatically. Export the variable (or `source .env` after adding `export`) before running.

## Architecture

Pure logic layer + thin adapters. The logic has no I/O imports, so a new adapter (web) was added without touching it — **keep this separation**. See `docs/web-app-plan.md` for the roadmap (DB/stats, chat, voice).

- **`game/game_logic.py`** — no Telegram/web imports, fully unit-testable. Contains all game state and rules:
  - `GameManager` holds `lobbies: Dict[str, Lobby]` entirely **in memory** (nothing is persisted; a restart wipes all lobbies). Lobby IDs are random 4-digit strings.
  - `Lobby` is the core state machine, driven by two flags: `game_started` and `game_stopped`. Nearly every method returns `bool`/`None` as a guard result, and the adapters rely on those return values for validation rather than re-checking state itself.
  - `end_game()` and `start_game()` reset all per-round fields; a single `Lobby` is reused across rounds.
- **`game/workplaces.py`** — the base `WORKPLACES` list (in Russian). Lobbies merge these with per-lobby `custom_workplaces`.

- **`adapters/telegram/bot.py`** — async command/callback handlers, each a thin wrapper that locates the relevant `Lobby` and calls into the logic. A single module-level `game_manager` global holds all state (tests reset it with `bot.game_manager = GameManager()`).

- **`adapters/web/`** — FastAPI adapter. `app.py` exposes REST (`POST /api/lobby`, `GET /api/lobby/{id}`, `GET /api/users/{id}/stats`) and a `/ws/{lobby_id}` WebSocket; `ws_manager.py` is the web analog of `broadcast_to_lobby`; `protocol.py` builds **per-user** state snapshots (roles are hidden — `build_state` is called once per socket). After every action the whole lobby state is rebroadcast and the `frontend/` (vanilla JS) re-renders. The `chat` action is the exception — it's a separate message stream (`{type:"chat"}`) that does **not** trigger a state rebroadcast, and the frontend keeps its chat panel in a section outside `#game` so re-renders don't wipe it. `_resolve_round` in `app.py` is the single place a round ends; it captures the participant/winner snapshot **before** `end_game()` resets roles, then records the game. Identity is a guest UUID from `localStorage`, passed as the `user_id` query param — note web user IDs are **strings**, unlike the bot's int IDs.

- **`persistence/`** — async SQLAlchemy + SQLite (phase 2). `models.py` stores raw rows (`User`, `Game`, `GamePlayer`); win/loss stats are computed by query in `stats_service.py` (no materialized counts to drift). `db.py` lazily builds the engine and exposes `configure(url)` so tests can point at a temp DB; the schema is created via `init_db()` in the app's `lifespan` (no Alembic yet). Stats writes are wrapped in `try/except` in `app.py` so a DB failure never breaks gameplay. **Keep DB access out of `game/`** — only the web adapter touches `persistence`.

### Key conventions and gotchas

- **A user is found by scanning all lobbies** for their `user_id` (see the repeated `for lobby in game_manager.lobbies.values()` blocks). There is no user→lobby index; effectively a user participates in one lobby at a time, and the organizer is matched separately via `is_organizer`.
- **All gameplay happens in private chats.** `broadcast_to_lobby` sends a DM to each player's `user_id`, so every player must have started a private chat with the bot. There is no group-chat game flow.
- **Inline-button callback data is `_`-delimited** and parsed by splitting in `button_handler`: `stop_<lobbyid>`, `accuse_<lobbyid>_<userid>`, `vote_<lobbyid>_<yes|no>`. This works only because lobby IDs and user IDs are numeric — do not put free-form text (e.g. workplace names) into callback data.
- **Two ways to win, two code paths:**
  1. A *worker* accuses someone via the inline button → `stop_game_by_worker` resolves the round immediately (correct accusation = workers win).
  2. The *spy* stops the game → `/guess <place>` → `set_spy_guess` opens a vote → workers vote via buttons → `get_vote_result` resolves it. The vote only resolves once **every** worker has voted; majority "yes" = spy wins.
  - The organizer can also override at any time with `/win workers|spy` or `/endgame`.
- **Minimum 3 players** to start (`start_game` returns `False` otherwise).
- **All user-facing strings and workplace names are in Russian.** Keep new strings in Russian for consistency.

### Testing approach

`tests/test_bot.py` stubs out the `telegram` / `telegram.ext` modules at import time if `python-telegram-bot` is not installed, so the handler tests run even without the dependency. Handlers are exercised with `FakeMessage`/`FakeBot` and `SimpleNamespace` updates. `tests/test_game_logic.py` patches `game.game_logic.random.choice` to make spy/workplace selection deterministic — use the same pattern when testing anything involving randomness. `tests/test_web.py` and `tests/test_stats.py` drive the web adapter via the shared `tests/web_base.py` `WebTestBase` (skipped if `fastapi`/`sqlalchemy` are missing). It enters the `TestClient` as a context manager so the `lifespan` runs `init_db` against a fresh temp SQLite DB per test, and `db.configure(...)` repoints the engine. Note each connect/action broadcasts exactly one state message **per connected socket**, so the `drain(ws, n)` helper reads a deterministic count rather than looping until a predicate.
