# Artha

voice finance agent that understands hinglish. tell it you spent 500 on chai, it logs it.

```
mic → whisper → llama 3.3 70b → tools → sarvam tts → speaker
```

---

## setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY and SARVAM_API_KEY (both free)
python server.py       # localhost:7860
```

---

## how it works

3-tier intent classifier. greeting regex first, then finance keywords, then LLM fallback for the ~10% of inputs that are ambiguous ("mujhe macbook kharidna hai" type stuff). finance goes to the agent loop, general chat streams token by token with per-sentence TTS.

memory syncs after every finance turn not just on disconnect. found out the hard way that if you only sync on disconnect and the user just closes the tab, you lose everything from that session.

barge-in: mic stays active during TTS playback, samples the first ~1.3s of bleed-through to set a threshold dynamically. so it works on headphones and laptop speakers without needing to hardcode anything. when you interrupt, playback stops immediately and a generation counter increments server-side. anything in-flight from the previous turn just drops itself.

ledger writes are atomic. load happens inside the lock not outside it, otherwise two concurrent sessions can read the same state and one write gets lost.

---

## stack

| | |
|---|---|
| STT | Groq Whisper large-v3 |
| LLM | Groq Llama 3.3 70B |
| TTS | Sarvam Bulbul v3 |
| backend | FastAPI + WebSocket |

---

## tests

```bash
GROQ_API_KEY=dummy SARVAM_API_KEY=dummy pytest tests/ -v
python evals/run_eval.py
```