import pytest
from dotenv import load_dotenv
load_dotenv()
from intent import classify


def test_greeting_basic():
    for w in ["hello", "hi", "namaste", "pranam"]:
        assert classify(w) == "general"

def test_greeting_extended():
    for p in ["hey there", "good morning", "good evening", "good afternoon"]:
        assert classify(p) == "general", f"'{p}' should be general"

def test_hindi_finance():
    for t in ["mera balance check karo", "kitna kharch hua", "paise kahan gaye", "EMI set karo"]:
        assert classify(t) == "finance"

def test_english_finance():
    for t in ["check my expenses", "log 500 for groceries", "can I afford this phone"]:
        assert classify(t) == "finance"

def test_general():
    for t in ["what is the capital of india", "tell me a joke", "how are you"]:
        assert classify(t) == "general"

def test_empty():
    assert classify("") == "general"
    assert classify("   ") == "general"

def test_always_valid_label():
    for t in ["mujhe MacBook kharidna hai", "kuch bhi", "123", "!@#$"]:
        assert classify(t) in ("finance", "general")
