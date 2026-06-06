import json
from pathlib import Path
from dataclasses import dataclass, asdict, field, fields
from datetime import datetime, timezone

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)


@dataclass
class Memory:
    summary: str = ""
    goals: list = field(default_factory=list)
    commitments: list = field(default_factory=list)
    observed_patterns: list = field(default_factory=list)
    user_profile: dict = field(default_factory=dict)
    last_updated: str = ""


def load_memory(user_id: str) -> Memory:
    path = MEMORY_DIR / f"{user_id}.json"
    try:
        if not path.exists():
            return Memory()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid = {fi.name for fi in fields(Memory)}
        return Memory(**{k: v for k, v in data.items() if k in valid})
    except Exception as e:
        print(f"[Memory] load failed: {e}")
        return Memory()


def save_memory(user_id: str, memory: Memory) -> bool:
    path = MEMORY_DIR / f"{user_id}.json"
    try:
        memory.last_updated = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(memory), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Memory] save failed: {e}")
        return False


def build_transcript(messages: list[dict]) -> str:
    lines = []
    for msg in messages:
        if msg.get("role") not in ("user", "assistant"):
            continue
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{msg['role']}: {content}")
    return "\n".join(lines)
