import re
import json
from memory import load_memory, save_memory, build_transcript, Memory
from tools.finance import log_expense, get_monthly_summary, check_budget, set_reminder, make_plan
from tools.search import search
from intent import classify
from llm import call_llm_with_tools, call_llm_simple
from datetime import date

MAX_ITER = 6

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "Update user profile — name, monthly_income, or primary_goal. Call when user shares these.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_income": {"type": "string", "description": "Monthly income e.g. 19000, 80k, 2 lakh"},
                    "name": {"type": "string", "description": "User name"},
                    "primary_goal": {"type": "string", "description": "Primary financial goal"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_expense",
            "description": "Record an expense. Call when user says they spent money.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Positive number"},
                    "category": {"type": "string", "description": "e.g. food, petrol, rent"},
                    "note": {"type": "string", "description": "Optional note"},
                },
                "required": ["amount", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_summary",
            "description": "Income, expense, balance summary for a month.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer"},
                    "month": {"type": "integer", "description": "1-12"},
                },
                "required": ["year", "month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_budget",
            "description": "Check if user can afford something. Call when user asks 'can I buy X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Always convert before passing — '1 lakh' = 100000"},
                },
                "required": ["amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Save a reminder or bill due date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["title", "due_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_plan",
            "description": "Create a savings plan from income and current month expenses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "income": {"type": "number"},
                },
                "required": ["income"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for financial news or info online.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
]


def build_system_prompt(memory: Memory) -> str:
    today = date.today().isoformat()
    return f"""You are Artha — a personal voice finance agent.
Today: {today}

User profile: {memory.user_profile}
Summary: {memory.summary}
Goals: {memory.goals}
Commitments: {memory.commitments}
Patterns: {memory.observed_patterns}

Rules:
- Use tools when needed — never invent numbers
- When user mentions income or name, call update_profile immediately
- Never assume user's name if not known
- Respond in Hinglish — casual Hindi-English mix
- Keep responses short — 2-3 lines max for voice
- Always convert amounts to plain numbers before tool calls
- Never write <function=...> tags — always use proper tool_calls format
- Profile above is context only — use tools for fresh calculations
"""


def _exec_tool(name: str, args: dict, memory: Memory, user_id: str) -> dict:
    print(f"[TOOL] {name}({args})")
    try:
        if name == "update_profile":
            memory.user_profile.update(args)
            save_memory(user_id, memory)
            return {"status": "updated", "profile": memory.user_profile}

        if name == "log_expense":
            return log_expense(user_id, **args)

        if name == "get_monthly_summary":
            return get_monthly_summary(user_id, **args)

        if name == "check_budget":
            return check_budget(user_id, float(args.get("amount", 0)), memory)

        if name == "set_reminder":
            updated = set_reminder(memory, args["title"], args["due_date"])
            save_memory(user_id, updated)
            return {"status": "saved", "title": args["title"]}

        if name == "make_plan":
            from ledger import get_monthly_expenses
            today = date.today()
            expenses = get_monthly_expenses(user_id, today.year, today.month)
            return make_plan(args["income"], expenses)

        if name == "search":
            return {"result": search(args["query"])}

        return {"error": f"unknown tool: {name}"}

    except Exception as e:
        print(f"[TOOL] {name} failed: {e}")
        return {"error": str(e)}


def agent_turn(messages: list, memory: Memory, user_id: str) -> str:
    history = [{"role": "system", "content": build_system_prompt(memory)}] + messages

    error_counts: dict[str, int] = {}

    for _ in range(MAX_ITER):
        msg = call_llm_with_tools(history, TOOL_DEFS)
        if not msg:
            return "Kuch gadbad ho gayi — please try again."

        if not getattr(msg, "tool_calls", None):
            return msg.content or ""

        history.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": msg.tool_calls,
        })

        for call in msg.tool_calls:
            try:
                args = json.loads(call.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                args = {}
            result = _exec_tool(call.function.name, args, memory, user_id)

            # Circuit breaker: if same tool errors 2+ times, stop
            if "error" in result:
                error_counts[call.function.name] = error_counts.get(call.function.name, 0) + 1
                if error_counts[call.function.name] >= 2:
                    return f"Tool '{call.function.name}' mein problem aa rahi hai — please try again."

            history.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            })

    return "Itne saare tools use ho gaye — please try again."


def sync_memory(memory: Memory, messages: list) -> Memory:
    transcript = build_transcript(messages)
    if not transcript.strip():
        return memory

    prompt = [
        {
            "role": "system",
            "content": (
                "Extract memory from this finance conversation.\n"
                "Return ONLY valid JSON, no markdown.\n"
                '{"summary":"...","goals":[{"description":"...","status":"active"}],'
                '"commitments":[{"title":"...","due_date":"YYYY-MM-DD"}],'
                '"observed_patterns":[{"category":"...","observation":"..."}]}'
            ),
        },
        {"role": "user", "content": transcript},
    ]

    try:
        result = re.sub(r"```[\w]*\n?|```", "", call_llm_simple(prompt)).strip()
        data = json.loads(result)
        memory.summary = data.get("summary", memory.summary)
        memory.goals = data.get("goals", memory.goals)
        memory.commitments = data.get("commitments", memory.commitments)
        memory.observed_patterns = data.get("observed_patterns", memory.observed_patterns)
        print("[Memory] synced")
    except Exception as e:
        print(f"[Memory] sync failed: {e}")

    return memory
