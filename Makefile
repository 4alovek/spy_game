PYTHON ?= python
BOT_MODULE ?= adapters.telegram.bot
WEB_HOST ?= 127.0.0.1
WEB_PORT ?= 8000
LOG_FILE ?= bot.log
PID_FILE ?= .bot.pid

# TLS for LAN testing (microphone access requires HTTPS on non-localhost origins)
TLS_HOST ?= 0.0.0.0
CERT_DIR ?= certs
CERT_FILE ?= $(CERT_DIR)/cert.pem
KEY_FILE ?= $(CERT_DIR)/key.pem
# IP put into the certificate's subjectAltName; defaults to the machine's LAN IP
CERT_IP ?= $(shell ip -4 addr show 2>/dev/null | grep -oP '(?<=inet\s)192\.168\.\d+\.\d+' | head -n1)

.PHONY: run run-bg run-web run-web-tls certs test status logs stop restart

run:
	$(PYTHON) -m $(BOT_MODULE)

run-bg:
	nohup $(PYTHON) -m $(BOT_MODULE) > $(LOG_FILE) 2>&1 & echo $$! > $(PID_FILE)
	@echo "Bot started in background. PID: $$(cat $(PID_FILE))"

run-web:
	$(PYTHON) -m uvicorn adapters.web.app:app --host $(WEB_HOST) --port $(WEB_PORT) --reload

certs:
	@mkdir -p $(CERT_DIR)
	@if [ -z "$(CERT_IP)" ]; then \
		echo "Could not detect LAN IP; pass CERT_IP=<ip> explicitly"; exit 1; \
	fi
	openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
		-keyout $(KEY_FILE) -out $(CERT_FILE) \
		-subj "/CN=$(CERT_IP)" -addext "subjectAltName=IP:$(CERT_IP),IP:127.0.0.1"
	@echo "Self-signed cert generated for $(CERT_IP) in $(CERT_DIR)/"

run-web-tls: $(CERT_FILE)
	@echo "Serving https://$(CERT_IP):$(WEB_PORT) (accept the browser warning on each device)"
	$(PYTHON) -m uvicorn adapters.web.app:app --host $(TLS_HOST) --port $(WEB_PORT) \
		--ssl-keyfile $(KEY_FILE) --ssl-certfile $(CERT_FILE) --reload

$(CERT_FILE):
	@$(MAKE) certs

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
