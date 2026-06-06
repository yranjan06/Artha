import json
import threading
from datetime import date
from pathlib import Path

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(user_id: str) -> threading.Lock:
    with _locks_lock:
        if user_id not in _locks:
            _locks[user_id] = threading.Lock()
        return _locks[user_id]


def _path(user_id: str) -> Path:
    return MEMORY_DIR / f"{user_id}_ledger.json"


def load_ledger(user_id: str) -> list:
    p = _path(user_id)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Ledger] load failed: {e}")
        return []


def save_ledger(user_id: str, data: list) -> bool:
    with _get_lock(user_id):
        try:
            with open(_path(user_id), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Ledger] save failed: {e}")
            return False


def add_transaction(user_id: str, amount: float, category: str, note: str = "") -> bool:
    with _get_lock(user_id):
        # load INSIDE the lock so read-append-write is atomic
        ledger = load_ledger(user_id)
        ledger.append({
            "date": date.today().isoformat(),
            "amount": amount,
            "category": category,
            "note": note,
        })
        try:
            with open(_path(user_id), "w", encoding="utf-8") as f:
                json.dump(ledger, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Ledger] save failed: {e}")
            return False


def get_monthly_expenses(user_id: str, year: int, month: int) -> list:
    prefix = f"{year:04d}-{month:02d}-"
    return [tx for tx in load_ledger(user_id) if tx.get("date", "").startswith(prefix)]
