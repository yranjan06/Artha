import os
import tempfile
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

TARGET_SR = 16000


def process_audio(input_path: str) -> str | None:
    if not input_path or not os.path.exists(input_path):
        print(f"[Audio] file not found: {input_path}")
        return None

    try:
        audio, sr = sf.read(input_path)

        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        audio = audio.astype(np.float32)

        if sr != TARGET_SR:
            g = _gcd(TARGET_SR, sr)
            audio = resample_poly(audio, TARGET_SR // g, sr // g).astype(np.float32)

        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        sf.write(out, audio, TARGET_SR)
        return out

    except Exception as e:
        print(f"[Audio] processing failed: {e}")
        return None


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a
