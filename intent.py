import re
from llm import call_llm_simple

FINANCE_PATTERN = re.compile(
    r"(balance|transaction|bill|sav|spend|incom|expens|"
    r"goal|remind|invest|salary|afford|log\s+\d|"
    r"kharch|pais|bacha|emi|budget|mutual|fund)",
    re.IGNORECASE,
)

GREETING_PATTERN = re.compile(
    r"^(hi|hello|hey(\s+\w+)?|namaste|pranam|"
    r"good\s+(morning|evening|afternoon|night)|"
    r"yo|sup|hiya|kya\s+haal|kaisa\s+hai)[\s!.,]*$",
    re.IGNORECASE,
)


def classify(text: str) -> str:
    if not text or not text.strip():
        return "general"

    cleaned = text.strip()

    if GREETING_PATTERN.match(cleaned):
        return "general"

    if FINANCE_PATTERN.search(cleaned):
        return "finance"

    prompt = [
        {
            "role": "system",
            "content": (
                "Classify as finance or general.\n"
                "finance: money, goals, income, expenses, savings, bills, investments\n"
                "general: everything else\n"
                "Reply with exactly one word."
            ),
        },
        {"role": "user", "content": cleaned},
    ]
    try:
        result = call_llm_simple(prompt).strip().lower()
        if "finance" in result:
            return "finance"
    except Exception as e:
        print(f"[Intent] LLM fallback failed: {e}")

    return "general"
