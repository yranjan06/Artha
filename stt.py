import os
from llm import audio_client

MODEL = "whisper-large-v3"
MAX_FILE_MB = 25


def transcribe(audio_path: str) -> str | None:
    if not os.path.exists(audio_path):
        print(f"[STT] file not found: {audio_path}")
        return None

    if os.path.getsize(audio_path) / (1024 * 1024) > MAX_FILE_MB:
        print("[STT] file too large")
        try:
            os.remove(audio_path)
        except OSError:
            pass
        return None

    try:
        with open(audio_path, "rb") as f:
            resp = audio_client.audio.transcriptions.create(file=f, model=MODEL)
        return resp.text.strip() if resp and resp.text else None
    except Exception as e:
        print(f"[STT] failed: {e}")
        return None
    finally:
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except OSError:
            pass
