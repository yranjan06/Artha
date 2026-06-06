import pytest
from unittest.mock import patch
from datetime import date
from tools.finance import parse_income, check_budget, make_plan, get_monthly_summary
from memory import Memory


class TestParseIncome:
    def test_plain_int(self):        assert parse_income(50000) == 50000.0
    def test_plain_string(self):     assert parse_income("50000") == 50000.0
    def test_k_notation(self):       assert parse_income("80k") == 80000.0
    def test_lakh_notation(self):    assert parse_income("2 lakh") == 200000.0
    def test_hazaar_notation(self):  assert parse_income("80 hazaar") == 80000.0
    def test_comma_separators(self): assert parse_income("80,000") == 80000.0
    def test_invalid(self):          assert parse_income("abc") == 0.0
    def test_none(self):             assert parse_income(None) == 0.0
    def test_empty(self):            assert parse_income("") == 0.0


class TestCheckBudget:
    def _mem(self, inc=None):
        m = Memory()
        if inc: m.user_profile = {"monthly_income": str(inc)}
        return m

    @patch("tools.finance.get_monthly_expenses")
    def test_can_afford(self, mock):
        mock.return_value = [{"amount": -5000, "category": "food", "date": "2025-05-01"}]
        r = check_budget("u1", 10000, self._mem(50000))
        assert r["can_afford"] is True and r["remaining"] == 45000.0

    @patch("tools.finance.get_monthly_expenses")
    def test_cannot_afford(self, mock):
        mock.return_value = [{"amount": -48000, "category": "rent", "date": "2025-05-01"}]
        assert check_budget("u1", 5000, self._mem(50000))["can_afford"] is False

    def test_no_income(self):
        assert check_budget("u1", 5000, self._mem())["error"] == "income_not_set"

    @patch("tools.finance.get_monthly_expenses")
    def test_income_txs_not_counted_as_expense(self, mock):
        mock.return_value = [{"amount": 50000, "category": "salary"}, {"amount": -10000, "category": "rent"}]
        assert check_budget("u1", 5000, self._mem(50000))["remaining"] == 40000.0


class TestMakePlan:
    def test_basic(self):
        r = make_plan("80k", [{"amount": -5000, "category": "food"}, {"amount": -2000, "category": "petrol"}])
        assert r["possible_savings"] == 73000.0

    def test_zero_income(self):
        assert make_plan(0, [])["savings_rate"] == 0

    def test_overspend(self):
        assert make_plan("80k", [{"amount": -90000, "category": "rent"}])["possible_savings"] == 0

    def test_income_entries_ignored(self):
        r = make_plan("80k", [{"amount": -5000, "category": "food"}, {"amount": 50000, "category": "salary"}])
        assert r["expenses"] == 5000.0


class TestGetMonthlySummary:
    @patch("tools.finance.get_monthly_expenses")
    def test_summary(self, mock):
        mock.return_value = [{"amount": -5000, "category": "food"}, {"amount": -2000, "category": "petrol"}, {"amount": 50000, "category": "salary"}]
        r = get_monthly_summary("u1", 2025, 5)
        assert r["total_income"] == 50000 and r["total_expense"] == 7000
        assert "salary" not in r["by_category"]
        assert r["income_sources"]["salary"] == 50000

    @patch("tools.finance.get_monthly_expenses")
    def test_empty(self, mock):
        mock.return_value = []
        r = get_monthly_summary("u1", 2025, 5)
        assert r["total_income"] == 0 and r["total_expense"] == 0
