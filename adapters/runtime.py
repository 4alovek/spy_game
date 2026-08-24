"""Точка запуска единого runtime: FastAPI и Telegram polling в одном процессе."""
from adapters.web.app import app

__all__ = ["app"]
