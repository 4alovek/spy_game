"""Канонические, несовпадающие между адаптерами идентификаторы игроков."""
import uuid


def web_user_id(raw_id: str) -> str:
    """Проверить guest UUID, полученный из localStorage, и добавить namespace."""
    try:
        value = str(uuid.UUID(str(raw_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Некорректный идентификатор гостя") from exc
    return f"web:{value}"


def telegram_user_id(raw_id: int) -> str:
    return f"tg:{int(raw_id)}"
