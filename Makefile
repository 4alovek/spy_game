PYTHON ?= python
BOT_FILE ?= bot.py
LOG_FILE ?= bot.log
PID_FILE ?= .bot.pid

.PHONY: run run-bg status logs stop restart

run:
	$(PYTHON) ./$(BOT_FILE)

run-bg:
	nohup $(PYTHON) ./$(BOT_FILE) > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE)
	@echo "Bot started in background. PID: $$(cat $(PID_FILE))"

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
