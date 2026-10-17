import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict

from config import BASE_DIR, settings

log = logging.getLogger(__name__)

_PATH = Path(BASE_DIR) / "data" / "users.json"
_lock = threading.Lock()


def _defaults() -> Dict[str, Any]:
    return {
        "balance": 500.0,
        "risk_percent": settings.DEFAULT_RISK_PERCENT,
        "timeframe": settings.DEFAULT_TIMEFRAME,
        "price_offset": 0.0,  # broker narxi - manba narxi
    }


def _load() -> Dict[str, Dict[str, Any]]:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        log.warning("Foydalanuvchi sozlamalari o'qilmadi: %s", exc)
        return {}


_users: Dict[str, Dict[str, Any]] = _load()


def _persist() -> None:
    """Atomik yozish: vaqtinchalik faylga yozib, so'ng almashtiriladi."""
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=_PATH.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(_users, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _PATH)
    except Exception as exc:
        log.error("Sozlamalarni saqlab bo'lmadi: %s", exc)


def get_settings(user_id: int) -> Dict[str, Any]:
    """Foydalanuvchi sozlamalarining nusxasini qaytaradi."""
    with _lock:
        return {**_defaults(), **_users.get(str(user_id), {})}


def update_settings(user_id: int, **changes: Any) -> Dict[str, Any]:
    """Sozlamalarni yangilaydi va yangi nusxani qaytaradi."""
    with _lock:
        current = {**_defaults(), **_users.get(str(user_id), {})}
        updated = {**current, **changes}
        _users[str(user_id)] = updated
        _persist()
        return dict(updated)
