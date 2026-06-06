import os
import re
import base64
import tempfile
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.sarvam.ai/text-to-speech"
MAX_CHARS = 500

_HINDI_SCRIPT = re.compile(r"[\u0900-\u097F]")
_HINDI_WORDS = re.compile(
    r"\b(hai|hain|kya|mera|tera|aur|par|se|ko|ka|ki|ke|main|mujhe|"
    r"yeh|woh|karo|hua|gaya|lakh|hazaar|paisa|paise|bhai|yaar|"
    r"hoga|hogi|chahiye|bahut|thoda|acha|sahi|nahi|nahin|bilkul|"
    r"namaste|theek|kitna|kahan|kaisa|dekho|suno|arre|abhi)\b",
    re.IGNORECASE,
)
_MARKDOWN = re.compile(r"[*_`#~\[\]<>]|```[\s\S]*?```|`[^`]+`")


def _clean(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _MARKDOWN.sub("", text)).strip()[:MAX_CHARS]


def _lang(text: str) -> str:
    if _HINDI_SCRIPT.search(text):
        return "hi-IN"
    return "hi-IN" if len(_HINDI_WORDS.findall(text)) > 1 else "en-IN"


def _call_sarvam(text: str) -> str | None:
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        print("[TTS] SARVAM_API_KEY not set — skipping TTS")
        return None

    if not text or not text.strip():
        return None

    cleaned = _clean(text)
    if not cleaned:
        return None

    lang = _lang(cleaned)
    print(f"[TTS] lang={lang}, len={len(cleaned)}")

    try:
        resp = requests.post(
            API_URL,
            headers={"api-subscription-key": api_key, "Content-Type": "application/json"},
            json={
                "text": cleaned,
                "target_language_code": lang,
                "model": "bulbul:v3",
                "speaker": "priya",
                "speech_sample_rate": 16000,
                "enable_preprocessing": True,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            print(f"[TTS] API {resp.status_code}: {resp.text[:200]}")
            return None

        audios = resp.json().get("audios")
        if not audios or not audios[0]:
            print("[TTS] empty audios in response")
            return None

        raw = audios[0]
        if isinstance(raw, str) and raw.startswith("data:"):
            raw = raw.split(",", 1)[1]

        audio_bytes = base64.b64decode(raw)
        if len(audio_bytes) < 100:
            print("[TTS] audio suspiciously small")
            return None

        return raw

    except requests.Timeout:
        print("[TTS] request timed out")
        return None
    except Exception as e:
        print(f"[TTS] failed: {e}")
        return None


def speak(text: str) -> str | None:
    raw = _call_sarvam(text)
    if not raw:
        return None
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(base64.b64decode(raw))
    return path


def speak_b64(text: str) -> str | None:
    return _call_sarvam(text)
