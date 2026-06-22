PYTHON ?= python
BOT_MODULE ?= adapters.telegram.bot
WEB_HOST ?= 127.0.0.1
WEB_PORT ?= 8000
LOG_FILE ?= bot.log
PID_FILE ?= .bot.pid

.PHONY: run run-bg run-web test status logs stop restart

run:
	$(PYTHON) -m $(BOT_MODULE)

run-bg:
	nohup $(PYTHON) -m $(BOT_MODULE) > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE)
	@echo "Bot started in background. PID: $$(cat $(PID_FILE))"

run-web:
	$(PYTHON) -m uvicorn adapters.web.app:app --host $(WEB_HOST) --port $(WEB_PORT) --reload

test:
	$(PYTHON) -m unittest discover -s tests

status:
	@if [ -f "$(PID_FILE)" ] && ps -p "$$(cat $(PID_FILE))" > /dev/null 2>&1; then \
		echo "Bot is running. PID: $$(cat $(PID_FILE))"; \
	else \
		echo "Bot is not running"; \
	fi

logs:
	@if [ -f "$(LOG_FILE)" ]; then \
		tail -n 100 -f "$(LOG_FILE)"; \
	else \
		echo "Log file not found: $(LOG_FILE)"; \
	fi

stop:
	@if [ -f "$(PID_FILE)" ] && ps -p "$$(cat $(PID_FILE))" > /dev/null 2>&1; then \
		kill "$$(cat $(PID_FILE))" && rm -f "$(PID_FILE)"; \
		echo "Bot stopped"; \
	else \
		echo "Bot is not running"; \
	fi

restart: stop run-bg
