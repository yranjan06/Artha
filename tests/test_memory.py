import os
import pytest
from pathlib import Path
from memory import Memory, save_memory, load_memory, build_transcript

_UID = "_pytest_artha_"

@pytest.fixture(autouse=True)
def cleanup():
    p = Path("memory") / f"{_UID}.json"
    if p.exists(): os.remove(p)
    yield
    if p.exists(): os.remove(p)

def test_roundtrip():
    m = Memory(); m.user_profile = {"name": "Rahul"}; save_memory(_UID, m)
    assert load_memory(_UID).user_profile["name"] == "Rahul"

def test_missing_returns_empty():
    assert isinstance(load_memory("__no_such_user__"), Memory)

def test_last_updated_set():
    save_memory(_UID, Memory())
    assert load_memory(_UID).last_updated != ""

def test_transcript_filters_system_tool():
    msgs = [
        {"role": "system",    "content": "You are Artha"},
        {"role": "user",      "content": "mera balance"},
        {"role": "assistant", "content": "45000 hai"},
        {"role": "tool",      "content": '{"result":45000}'},
    ]
    tx = build_transcript(msgs)
    assert "mera balance" in tx and "45000 hai" in tx
    assert "system" not in tx and "tool" not in tx

def test_transcript_skips_empty():
    msgs = [{"role": "user", "content": ""}, {"role": "assistant", "content": "Namaste!"}]
    assert build_transcript(msgs).strip() == "assistant: Namaste!"
