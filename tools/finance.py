from datetime import date
from ledger import add_transaction, get_monthly_expenses


def parse_income(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value:
        return 0.0

    cleaned = value.lower().replace(",", "").strip()
    multiplier = 1

    if "crore" in cleaned:
        multiplier = 10_000_000
        cleaned = cleaned.replace("crore", "")
    elif "lakh" in cleaned or "lac" in cleaned:
        multiplier = 100_000
        cleaned = cleaned.replace("lakh", "").replace("lac", "")
    elif "hazaar" in cleaned or "hazar" in cleaned:
        multiplier = 1_000
        cleaned = cleaned.replace("hazaar", "").replace("hazar", "")
    elif cleaned.endswith("k"):
        multiplier = 1_000
        cleaned = cleaned[:-1]

    try:
        return float(cleaned.strip()) * multiplier
    except ValueError:
        return 0.0


def log_expense(user_id: str, amount: float, category: str, note: str = "") -> dict:
    add_transaction(user_id, -abs(amount), category, note)
    return {"status": "ok", "message": f"{abs(amount)} logged under {category}"}


def get_monthly_summary(user_id: str, year: int, month: int) -> dict:
    txs = get_monthly_expenses(user_id, year, month)
    total_income = total_expense = 0.0
    by_category = {}
    income_sources = {}

    for tx in txs:
        amt = tx.get("amount", 0)
        cat = tx.get("category", "other")
        if amt >= 0:
            total_income += amt
            income_sources[cat] = income_sources.get(cat, 0.0) + amt
        else:
            abs_amt = abs(amt)
            total_expense += abs_amt
            by_category[cat] = by_category.get(cat, 0.0) + abs_amt

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": total_income - total_expense,
        "by_category": by_category,
        "income_sources": income_sources,
        "tx_count": len(txs),
    }


def check_budget(user_id: str, amount: float, memory) -> dict:
    income_raw = memory.user_profile.get("monthly_income")
    if not income_raw:
        return {"error": "income_not_set", "message": "Pehle apni monthly income batao."}

    income = parse_income(income_raw)
    if income <= 0:
        return {"error": "income_invalid", "message": "Income valid number mein batao (e.g. 50000 or 50k)."}

    today = date.today()
    txs = get_monthly_expenses(user_id, today.year, today.month)
    spent = sum(abs(tx["amount"]) for tx in txs if tx["amount"] < 0)
    remaining = max(income - spent, 0.0)

    return {
        "can_afford": remaining >= amount,
        "remaining": remaining,
        "requested": amount,
        "income": income,
        "spent_so_far": spent,
    }


def set_reminder(memory, title: str, due_date: str):
    memory.commitments.append({"title": title, "due_date": due_date, "status": "pending"})
    return memory


def make_plan(income, expenses_list: list) -> dict:
    income = parse_income(income)
    total_expense = sum(abs(tx["amount"]) for tx in expenses_list if tx["amount"] < 0)
    possible_sav = max(income - total_expense, 0.0)
    rate = round((possible_sav / income) * 100, 1) if income > 0 else 0.0
    return {"income": income, "expenses": total_expense, "possible_savings": possible_sav, "savings_rate": rate}
