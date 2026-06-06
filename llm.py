import os
import time
from openai import OpenAI
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL = "llama-3.3-70b-versatile"

_key = os.getenv("GROQ_API_KEY")
if not _key:
    raise RuntimeError("GROQ_API_KEY missing — add to .env")

# Chat client (OpenAI SDK → Groq endpoint)
chat_client = OpenAI(api_key=_key, base_url="https://api.groq.com/openai/v1")

# Audio client (Groq SDK — needed for Whisper)
audio_client = Groq(api_key=_key)


def call_llm_with_tools(messages, tool_defs, max_retries=2):
    attempt_msgs = list(messages)

    for attempt in range(max_retries):
        try:
            resp = chat_client.chat.completions.create(
                model=MODEL,
                messages=attempt_msgs,
                tools=tool_defs,
                tool_choice="auto",
            )
            return resp.choices[0].message

        except Exception as e:
            err = str(e)
            is_tool_err = "tool_use_failed" in err or "Failed to call a function" in err

            if attempt < max_retries - 1:
                if is_tool_err:
                    for i in range(len(attempt_msgs) - 1, -1, -1):
                        if attempt_msgs[i]["role"] == "user":
                            orig = attempt_msgs[i]["content"] or ""
                            attempt_msgs[i] = {
                                "role": "user",
                                "content": orig + "\n\n[SYSTEM: malformed tool call — use proper JSON tool_calls format, not <function=...> tags]",
                            }
                            break
                time.sleep(0.5 if is_tool_err else 1)
                continue

            print(f"[LLM] failed after {max_retries} attempts: {e}")
            return None

    return None


def call_llm_simple(messages, max_retries=2):
    for attempt in range(max_retries):
        try:
            resp = chat_client.chat.completions.create(model=MODEL, messages=messages)
            return resp.choices[0].message.content or ""
        except Exception as e:
            print(f"[LLM] simple call attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
    return ""


def call_llm_simple_stream(messages):
    try:
        resp = chat_client.chat.completions.create(
            model=MODEL, messages=messages, stream=True
        )
        for chunk in resp:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
    except Exception as e:
        print(f"[LLM] stream failed: {e}")
        yield "Kuch gadbad ho gayi — please try again."
