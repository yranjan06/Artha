import os
import re
import json
import base64
import asyncio
import tempfile
import wave
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from agent import agent_turn, sync_memory, build_system_prompt
from memory import load_memory, save_memory
from onboarding import needs_onboarding
from stt import transcribe
from tts import speak, speak_b64
from intent import classify
from llm import call_llm_simple, call_llm_simple_stream
from utils.audio import process_audio
from ledger import get_monthly_expenses

app = FastAPI(title="Artha v3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
Path("memory").mkdir(exist_ok=True)

# Per-user session store — prevents split-brain when a user opens two tabs.
# Maps user_id -> {"messages": list, "lock": asyncio.Lock, "active": bool}
_sessions: dict[str, dict] = {}


def _get_session(user_id: str) -> dict:
    if user_id not in _sessions:
        _sessions[user_id] = {
            "messages": [],
            "lock": asyncio.Lock(),
            "active": False,
            "gen": 0,  # incremented on each barge-in to cancel stale replies
        }
    return _sessions[user_id]


_SENTENCE_RE = re.compile(r'(?<=[.!?।])(\s+)')


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_RE.split(text)
    sentences, current = [], ""
    for part in parts:
        current += part
        if current.strip() and _SENTENCE_RE.search(current):
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())
    return sentences if sentences else [text.strip()] if text.strip() else []


async def _push_dashboard(ws: WebSocket, user_id: str):
    try:
        from tools.finance import get_monthly_summary, parse_income

        today = date.today()
        summary = get_monthly_summary(user_id, today.year, today.month)
        recent = get_monthly_expenses(user_id, today.year, today.month)[-10:]

        mem = load_memory(user_id)
        income = summary["total_income"] or parse_income(mem.user_profile.get("monthly_income", ""))
        exp = summary["total_expense"]
        rate = round(((income - exp) / income * 100), 1) if income > 0 else 0.0

        await ws.send_text(json.dumps({
            "type": "dashboard_update",
            "data": {
                "total_income": income,
                "total_expense": exp,
                "by_category": summary["by_category"],
                "savings_rate": rate,
                "recent_tx": recent,
            },
        }))
    except Exception as e:
        print(f"[Dashboard] push failed: {e}")


async def _handle_transcript(
    transcript: str, messages: list, memory, user_id: str,
    ws: WebSocket, session_mode: str, gen_id: int = 0
):
    print(f"[WS] transcript: {transcript!r}")
    await ws.send_text(json.dumps({"type": "transcript", "text": transcript}))
    messages.append({"role": "user", "content": transcript})
    await ws.send_text(json.dumps({"type": "status", "state": "thinking"}))

    loop = asyncio.get_event_loop()
    intent = await loop.run_in_executor(None, classify, transcript)
    print(f"[WS] intent: {intent}")
    await ws.send_text(json.dumps({"type": "decision", "intent": intent}))

    # Check if user barged-in while we were classifying
    if _get_session(user_id)["gen"] != gen_id:
        print(f"[WS] reply cancelled by barge-in (classify stage) for {user_id}")
        return

    if intent == "finance":
        reply = await loop.run_in_executor(None, agent_turn, messages, memory, user_id)
        await _push_dashboard(ws, user_id)

        # Memory sync after every finance turn
        try:
            updated, ok = await loop.run_in_executor(None, sync_memory, memory, messages)
            if ok:
                memory.summary = updated.summary
                memory.goals = updated.goals
                memory.commitments = updated.commitments
                memory.observed_patterns = updated.observed_patterns
                save_memory(user_id, memory)
            else:
                print(f"[Memory] per-turn sync failed for {user_id} — memory not updated")
        except Exception as e:
            print(f"[Memory] per-turn sync error: {e}")

        # Final cancellation check before sending audio — covers mid-tool-call barge-in
        if _get_session(user_id)["gen"] != gen_id:
            print(f"[WS] reply cancelled by barge-in (post-tool) for {user_id}")
            return

        print(f"[WS] reply: {reply[:120]!r}")
        messages.append({"role": "assistant", "content": reply})
        await _send_audio(ws, reply, session_mode)
    else:
        await _handle_stream(messages, memory, ws, session_mode, gen_id, user_id)


async def _handle_stream(messages: list, memory, ws: WebSocket, session_mode: str, gen_id: int = 0, user_id: str = ""):
    llm_messages = [
        {"role": "system", "content": build_system_prompt(memory)},
        *messages,
    ]

    full_reply = ""
    sentence_buf = ""
    chunk_index = 0
    tts_tasks = []

    for token in call_llm_simple_stream(llm_messages):
        full_reply += token
        sentence_buf += token

        # Drop stream mid-way if barged-in
        if user_id and _get_session(user_id)["gen"] != gen_id:
            print(f"[WS] stream cancelled by barge-in for {user_id}")
            return

        await ws.send_text(json.dumps({"type": "stream_text", "text": token}))

        if _SENTENCE_RE.search(sentence_buf):
            sentences = _split_sentences(sentence_buf)
            if not _SENTENCE_RE.search(sentences[-1]):
                sentence_buf = sentences.pop()
            else:
                sentence_buf = ""

            for sent in sentences:
                idx = chunk_index
                chunk_index += 1
                if session_mode == "mic":
                    task = asyncio.create_task(_tts_and_send(ws, sent, idx, user_id, gen_id))
                    tts_tasks.append(task)

    if sentence_buf.strip():
        if session_mode == "mic":
            task = asyncio.create_task(_tts_and_send(ws, sentence_buf.strip(), chunk_index, user_id, gen_id))
            tts_tasks.append(task)

    if tts_tasks:
        await asyncio.gather(*tts_tasks, return_exceptions=True)

    await ws.send_text(json.dumps({"type": "stream_end"}))
    print(f"[WS] streamed reply: {full_reply[:120]!r}")
    messages.append({"role": "assistant", "content": full_reply})


async def _tts_and_send(ws: WebSocket, text: str, index: int, user_id: str = "", gen_id: int = 0):
    # Discard this chunk if the user has already barged in
    if user_id and _get_session(user_id)["gen"] != gen_id:
        print(f"[TTS-stream] chunk {index} cancelled by barge-in")
        return
    try:
        loop = asyncio.get_event_loop()
        audio_b64 = await loop.run_in_executor(None, speak_b64, text)
        if audio_b64:
            await ws.send_text(json.dumps({
                "type": "stream_audio",
                "data": audio_b64,
                "text": text,
                "index": index,
            }))
        else:
            await ws.send_text(json.dumps({
                "type": "stream_audio_fallback",
                "text": text,
                "index": index,
            }))
    except Exception as e:
        print(f"[TTS-stream] chunk {index} failed: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0"}


@app.get("/")
async def root():
    return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))


@app.get("/api/dashboard")
async def dashboard_api(user_id: str = "default", year: int = None, month: int = None):
    try:
        from tools.finance import get_monthly_summary, parse_income

        now = date.today()
        y, m = year or now.year, month or now.month
        summary = get_monthly_summary(user_id, y, m)
        recent = get_monthly_expenses(user_id, y, m)[-10:]
        mem = load_memory(user_id)
        income = summary["total_income"] or parse_income(mem.user_profile.get("monthly_income", ""))
        exp = summary["total_expense"]
        rate = round(((income - exp) / income * 100), 1) if income > 0 else 0.0

        return {
            "total_income": income,
            "total_expense": exp,
            "by_category": summary["by_category"],
            "savings_rate": rate,
            "recent_tx": recent,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/feedback")
async def save_feedback(request: Request):
    try:
        data = await request.json()
        uid = data.get("user_id", "default")
        memory = load_memory(uid)
        if "feedback_history" not in memory.user_profile:
            memory.user_profile["feedback_history"] = []
        memory.user_profile["feedback_history"].append({
            "date": date.today().isoformat(),
            "mood": data.get("mood", ""),
            "slider_value": data.get("slider_value", 50),
            "note": data.get("note", ""),
        })
        save_memory(uid, memory)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


@app.websocket("/ws/{user_id}")
async def ws_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    print(f"[WS] session start: {user_id}")

    session = _get_session(user_id)

    # Reject duplicate concurrent connections for the same user
    if session["active"]:
        await websocket.send_text(json.dumps({
            "type": "error",
            "text": "Another session is already active. Close the other tab first.",
        }))
        await websocket.close()
        return

    session["active"] = True
    session["messages"] = []  # fresh conversation per session
    messages = session["messages"]

    memory = load_memory(user_id)
    session_mode = None  # locked after first message
    audio_buffer = bytearray()
    client_sample_rate = 16000

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            # === Session start — lock mode ===
            if msg.get("type") == "session_start":
                session_mode = msg.get("mode", "text")
                print(f"[WS] mode locked: {session_mode}")

                welcome = (
                    "Namaste! Main Artha hun — aapka personal finance agent. Pehle apna naam aur monthly income batao."
                    if needs_onboarding(memory)
                    else f"Wapas aagaye{', ' + memory.user_profile.get('name', '') if memory.user_profile.get('name') else ''}! Kya update hai aaj?"
                )
                await _send_audio(websocket, welcome, session_mode)
                await _push_dashboard(websocket, user_id)
                continue

            if msg.get("type") == "end_session":
                await websocket.send_text(json.dumps({"type": "status", "state": "saving"}))
                updated, ok = sync_memory(memory, messages)
                if ok:
                    memory.summary = updated.summary
                    memory.goals = updated.goals
                    memory.commitments = updated.commitments
                    memory.observed_patterns = updated.observed_patterns
                save_memory(user_id, memory)
                await websocket.send_text(json.dumps({"type": "session_ended", "user_id": user_id}))
                break

            # === Barge-in: user interrupted bot mid-speech ===
            if msg.get("type") == "barge_in":
                session["gen"] += 1
                print(f"[WS] barge-in from {user_id} — gen now {session['gen']}, resetting audio buffer")
                audio_buffer = bytearray()  # discard partial audio from before interrupt
                continue

            # === Mode enforcement ===
            if msg.get("type") == "text":
                if session_mode == "mic":
                    await websocket.send_text(json.dumps({"type": "error", "text": "Mic mode active — use voice or end call first."}))
                    continue
                content = msg.get("content", "").strip()
                if content:
                    await _handle_transcript(content, messages, memory, user_id, websocket, session_mode or "text")

            elif msg.get("type") == "stream_audio_start":
                if session_mode == "text":
                    continue
                audio_buffer = bytearray()
                client_sample_rate = int(msg.get("sampleRate", 16000))

            elif msg.get("type") == "stream_audio_chunk":
                if session_mode == "text":
                    continue
                b64 = msg.get("data", "")
                if b64:
                    audio_buffer.extend(base64.b64decode(b64))

            elif msg.get("type") == "stream_audio_end":
                if session_mode == "text":
                    continue
                print(f"[WS] Audio stream ended, total bytes={len(audio_buffer)}")
                if len(audio_buffer) < 500:
                    continue

                fd, raw_path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                with wave.open(raw_path, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(client_sample_rate)
                    wav_file.writeframes(audio_buffer)

                processed = process_audio(raw_path)
                try:
                    os.remove(raw_path)
                except OSError:
                    pass

                if not processed:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "text": "Audio processing failed — please try again.",
                    }))
                    continue

                transcript = transcribe(processed)
                if not transcript:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "text": "Couldn't hear that — speak again.",
                    }))
                    continue

                # Snapshot gen at time of transcription — used to detect barge-ins
                # that arrive while agent_turn / TTS is running
                current_gen = session["gen"]
                await _handle_transcript(
                    transcript, messages, memory, user_id,
                    websocket, session_mode or "mic", current_gen
                )

    except WebSocketDisconnect:
        print(f"[WS] disconnect: {user_id}")
        if messages:
            updated, ok = sync_memory(memory, messages)
            if ok:
                memory.summary = updated.summary
                memory.goals = updated.goals
                memory.commitments = updated.commitments
                memory.observed_patterns = updated.observed_patterns
                save_memory(user_id, memory)
            else:
                print(f"[Memory] disconnect sync failed for {user_id} — last turn not saved")

    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_text(json.dumps({"type": "error", "text": str(e)[:100]}))
        except Exception:
            pass

    finally:
        session["active"] = False
        print(f"[WS] session end: {user_id}")


async def _send_audio(ws: WebSocket, text: str, session_mode: str = "mic"):
    if session_mode == "mic":
        audio_path = speak(text)
        if audio_path:
            try:
                audio_b64 = base64.b64encode(open(audio_path, "rb").read()).decode()
                await ws.send_text(json.dumps({"type": "audio", "text": text, "data": audio_b64}))
            except Exception as e:
                print(f"[TTS] send failed: {e}")
                await ws.send_text(json.dumps({"type": "text_only", "text": text}))
            finally:
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
        else:
            await ws.send_text(json.dumps({"type": "text_only", "text": text}))
    else:
        await ws.send_text(json.dumps({"type": "text_only", "text": text}))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=7860, reload=False)
