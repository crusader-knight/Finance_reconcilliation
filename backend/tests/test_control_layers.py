from decimal import Decimal
from types import SimpleNamespace

from app.analyst import ExceptionAnalyst
from app.policy import Policy, decide
from app.reconciliation import ReconciliationPolicy, compare, deterministic_score


def records(bank_amount=Decimal("9764.00"), bank_date=None):
    payment = SimpleNamespace(id="PAY-1", amount=Decimal("10000.00"), payment_date=__import__("datetime").date(2026, 8, 1), merchant_id="M-1", currency="INR")
    settlement = SimpleNamespace(net_amount=Decimal("9764.00"), gross_amount=Decimal("10000.00"), settlement_date=__import__("datetime").date(2026, 8, 2))
    bank = SimpleNamespace(amount=bank_amount, transaction_date=bank_date or __import__("datetime").date(2026, 8, 2), reference="PAY-1", merchant_id="M-1", currency="INR")
    return payment, settlement, bank


def test_fee_adjusted_evidence_is_transparent():
    match_type, _, _, evidence = compare(*records(), ReconciliationPolicy())
    score, factors = deterministic_score(evidence)
    assert match_type == "EXACT_CHAIN"
    assert score == Decimal("0.9500")
    assert any(item["name"] == "Reference" and item["status"] == "MATCH" for item in factors)


def test_amount_mismatch_goes_to_review():
    match_type, _, _, evidence = compare(*records(bank_amount=Decimal("9000")), ReconciliationPolicy())
    score, _ = deterministic_score(evidence)
    assert match_type == "AI_ASSISTED"
    assert decide(score, Decimal("10000"), False, False, Policy())[0] == "HUMAN_REVIEW"


def test_analyst_returns_strict_structured_result():
    result = ExceptionAnalyst().analyze({"fields": [{"field": "amount", "status": "MISMATCH"}], "bank_amount": "9000", "settlement_amount": "9764", "duplicate_signals": []})
    assert result.classification == "fee_mismatch"
    assert Decimal("0") <= result.confidence <= Decimal("1")
