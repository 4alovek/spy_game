# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A Telegram bot for the party game "Spy" (Шпион): players join a lobby, one is secretly assigned the spy, and the rest share a workplace. The spy tries to guess the workplace; the workers try to identify the spy.

## Commands

```bash
# Run the test suite (no Make target exists for tests)
python -m unittest discover -s tests

# Run a single test
python -m unittest tests.test_game_logic.LobbyGameLogicTests.test_start_game_assigns_one_spy_and_workplace_for_workers

# Run the bot (requires TELEGRAM_BOT_TOKEN in the environment)
make run            # foreground
make run-bg         # background (PID in .bot.pid, output to bot.log)
make status / make logs / make stop / make restart
```

There is no linter or formatter configured.

`bot.py` reads `TELEGRAM_BOT_TOKEN` via `os.getenv` only — there is **no** dotenv loading, so `make run` does not pick up `.env` automatically. Export the variable (or `source .env` after adding `export`) before running.

## Architecture

The code is split into a pure logic layer and a thin Telegram adapter — keep this separation when adding features.

- **`game_logic.py`** — no Telegram imports, fully unit-testable. Contains all game state and rules:
  - `GameManager` holds `lobbies: Dict[str, Lobby]` entirely **in memory** (nothing is persisted; a restart wipes all lobbies). Lobby IDs are random 4-digit strings.
  - `Lobby` is the core state machine, driven by two flags: `game_started` and `game_stopped`. Nearly every method returns `bool`/`None` as a guard result, and `bot.py` relies on those return values for validation rather than re-checking state itself.
  - `end_game()` and `start_game()` reset all per-round fields; a single `Lobby` is reused across rounds.

- **`bot.py`** — async command/callback handlers, each a thin wrapper that locates the relevant `Lobby` and calls into `game_logic`. A single module-level `game_manager` global holds all state (tests reset it with `bot.game_manager = GameManager()`).

- **`workplaces.py`** — the base `WORKPLACES` list (in Russian). Lobbies merge these with per-lobby `custom_workplaces` added via `/addplace`.

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

`tests/test_bot.py` stubs out the `telegram` / `telegram.ext` modules at import time if `python-telegram-bot` is not installed, so the handler tests run even without the dependency. Handlers are exercised with `FakeMessage`/`FakeBot` and `SimpleNamespace` updates. `tests/test_game_logic.py` patches `game_logic.random.choice` to make spy/workplace selection deterministic — use the same pattern when testing anything involving randomness.
