# Artha — Voice-First Personal Finance Agent

Talk to it in Hinglish. It tracks your money, checks your budget, and builds savings plans.

```
Browser mic → VAD silence detect → PCM stream → Groq Whisper → Llama 3.3 70B → tool calls → Sarvam TTS → Browser speaker
```

---

## Quick Start

```bash
# 1. Clone and create venv
python -m venv venv && source venv/bin/activate

# 2. Install deps
pip install -r requirements.txt

# 3. Add API keys
cp .env.example .env
# edit .env — add GROQ_API_KEY and SARVAM_API_KEY

# 4. Run
python server.py
# → http://localhost:7860
```

### API Keys (both free)

| Key | Where to get |
|-----|-------------|
| `GROQ_API_KEY` | https://console.groq.com |
| `SARVAM_API_KEY` | https://dashboard.sarvam.ai |

---

## How It Works

### Session model

User picks a username on first visit (stored in localStorage). Then chooses a mode:

- **Call mode** — real-time voice conversation with VAD-based silence detection and barge-in support
- **Text mode** — chat interface with live dashboard sidebar

Mode is locked for the entire session. No switching mid-session. Press "End Call" to save memory and return to the landing screen.

Per-user session state is tracked server-side — opening two tabs for the same username shows an error on the second tab rather than splitting the conversation context.

### Audio pipeline

Browser captures PCM audio via `ScriptProcessorNode`, computes RMS per frame for silence detection. When silence exceeds 700ms, the buffered audio is sent as a WAV over WebSocket:

```
Mic → ScriptProcessorNode → RMS silence detect
       ↓ speaking: Float32 → Int16 → base64 chunks
       ↓ silence 700ms: stream_audio_end
    WebSocket → server
       ↓ wave.open() → WAV file
    soundfile.read() → 16kHz mono
       ↓
    Groq Whisper STT → transcript
```

### Barge-in detection

While the assistant is speaking, the mic stays active at a higher RMS threshold. If the user speaks above that threshold, playback stops immediately and the user's speech is captured:

```
TTS playing → mic samples bleed-through RMS for ~1.3s → dynamic threshold = max(mean × 2.5, 0.015)
User speaks above threshold → currentAudio.pause() → queue cleared → barge_in sent to server
Server increments generation counter → any in-flight agent_turn or TTS chunks self-discard
```

**Known limitation:** dynamic threshold adapts per session but resets on each TTS chunk. Works well for headphones and laptop speakers; very loud external speakers may need manual tuning of `BARGE_IN_THRESHOLD_MIN` in `index.html`.

### Intent classifier (3-tier)

```
User input
  ↓
Tier 0: greeting regex  →  "general"
  ↓
Tier 1: finance keywords →  "finance"
  ↓
Tier 2: LLM fallback    →  "finance" | "general"
```

Tier 2 fires for ~10% of ambiguous queries. All classify calls run in `run_in_executor` to avoid blocking the async event loop.

### Agentic loop

```python
for _ in range(MAX_ITER):          # max 6 iterations
    msg = call_llm_with_tools(history, TOOL_DEFS)
    if not msg.tool_calls:
        return msg.content         # done
    for call in msg.tool_calls:
        result = exec_tool(call)
        if same_tool_errors >= 2:  # circuit breaker
            return error_message
        history.append(result)
```

### Post-turn pipeline (finance)

After every finance tool call, before the next user turn:
1. Log response
2. Push dashboard update via WebSocket
3. Sync memory (goals, patterns, commitments)
4. Save memory to disk

Memory sync returns `(Memory, bool)` — if LLM returns unparseable JSON, the old memory is kept and the failure is logged explicitly (not silently dropped).

### Audio playback

TTS chunks arrive out of order (parallel generation). Frontend queues them by `index` and plays sequentially — no garbled overlapping audio.

---

## Project Structure

```
artha/
├── server.py          FastAPI + WebSocket — mode lock, session management, barge-in handling
├── agent.py           Agentic loop with circuit breaker
├── intent.py          3-tier classifier
├── memory.py          Per-user JSON memory
├── ledger.py          Per-user transaction log with write locks (atomic read-append-write)
├── stt.py             Groq Whisper large-v3
├── tts.py             Sarvam Bulbul v3 (deduplicated)
├── llm.py             Single client for chat + audio
├── onboarding.py      First-session check
├── tools/
│   ├── finance.py     7 finance tools
│   └── search.py      DuckDuckGo fallback
├── utils/
│   └── audio.py       16kHz mono WAV normalisation
├── static/
│   └── index.html     Full UI — landing, call mode, text chat, dashboard
├── tests/             Unit tests (finance, intent, memory)
├── evals/
│   ├── intent_eval.json   14 labelled intent test cases
│   └── run_eval.py        Intent classifier eval runner
└── .github/workflows/ CI
```

---

## Tech Stack

| Component | Tech |
|-----------|------|
| STT | Groq Whisper large-v3 |
| LLM | Groq Llama 3.3 70B Versatile |
| TTS | Sarvam Bulbul v3 (hi-IN / en-IN auto-detect) |
| VAD | Browser-side RMS analysis via ScriptProcessorNode |
| Barge-in | Dynamic RMS baseline sampling — adapts to speaker bleed-through per session |
| Backend | FastAPI + WebSocket |
| Frontend | Vanilla JS, DM Sans, dark theme |
| Memory | Per-user JSON with write locks |

---

## Docker

```bash
docker-compose up --build
# → http://localhost:7860
```

## Tests

```bash
GROQ_API_KEY=dummy SARVAM_API_KEY=dummy pytest tests/ -v
```

## Eval

```bash
# Run intent classifier eval (no API key needed for tier 0/1, uses LLM for tier 2)
python evals/run_eval.py
```
