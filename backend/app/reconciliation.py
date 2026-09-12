from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ReconciliationPolicy:
    amount_tolerance: Decimal = Decimal("0.50")
    date_tolerance_days: int = 2
    fee_tolerance: Decimal = Decimal("0.50")


@dataclass(frozen=True)
class Evidence:
    fields: list[dict]
    amount_difference: Decimal
    date_difference: int | None
    rule: str
    rule_explanation: str
    duplicate_signals: list[str]

    def as_dict(self) -> dict:
        return {
            "fields": self.fields,
            "amount_difference": str(self.amount_difference),
            "date_difference": self.date_difference,
            "rule": self.rule,
            "rule_explanation": self.rule_explanation,
            "duplicate_signals": self.duplicate_signals,
        }


def compare(payment, settlement, bank, policy: ReconciliationPolicy, duplicates=None) -> tuple[str, str, Decimal, Evidence]:
    duplicates = duplicates or []
    settlement_amount = settlement.net_amount if settlement else None
    bank_amount = bank.amount if bank else None
    amount_difference = abs(payment.amount - bank_amount) if bank else payment.amount
    date_difference = abs((bank.transaction_date - payment.payment_date).days) if bank else None
    fields = [
        {"field": "reference", "status": "MATCH" if bank and bank.reference == payment.id else "MISSING" if not bank else "MISMATCH", "expected": payment.id, "actual": bank.reference if bank else None},
        {"field": "merchant", "status": "MATCH" if bank and bank.merchant_id == payment.merchant_id else "MISSING" if not bank else "MISMATCH", "expected": payment.merchant_id, "actual": bank.merchant_id if bank else None},
        {"field": "currency", "status": "MATCH" if bank and bank.currency == payment.currency else "MISSING" if not bank else "MISMATCH", "expected": payment.currency, "actual": bank.currency if bank else None},
        {"field": "amount", "status": "MATCH" if bank and abs(bank.amount - settlement_amount) <= policy.amount_tolerance else "MISSING" if not bank else "MISMATCH", "expected": str(settlement_amount) if settlement else None, "actual": str(bank_amount) if bank else None},
        {"field": "date", "status": "MATCH" if date_difference is not None and date_difference <= policy.date_tolerance_days else "MISSING" if not bank else "MISMATCH", "expected": str(payment.payment_date), "actual": str(bank.transaction_date) if bank else None},
    ]
    if not settlement or not bank:
        rule = "MISSING_RECORD"
        reason = "Settlement or bank transaction is missing"
        match_type = "NO_MATCH"
    elif payment.id == bank.reference and payment.amount == settlement.gross_amount and abs(bank.amount - settlement.net_amount) <= policy.amount_tolerance and date_difference <= policy.date_tolerance_days:
        rule, reason, match_type = "EXACT_CHAIN", "Payment, settlement and bank amount agree", "EXACT_CHAIN"
    elif payment.amount == settlement.gross_amount and abs(bank.amount - settlement.net_amount) <= policy.fee_tolerance and date_difference <= policy.date_tolerance_days:
        rule, reason, match_type = "FEE_ADJUSTED", "Net settlement agrees after gateway fee and tax", "FEE_ADJUSTED"
    elif bank.merchant_id == payment.merchant_id and payment.currency == bank.currency and date_difference <= policy.date_tolerance_days and abs(bank.amount - settlement.net_amount) <= policy.amount_tolerance:
        rule, reason, match_type = "MERCHANT_DATE_AMOUNT", "Merchant, currency, date and amount are within policy tolerance", "RULE_BASED"
    else:
        rule, reason, match_type = "CONFLICTING_EVIDENCE", "Conflicting evidence requires human verification", "AI_ASSISTED"
    return match_type, reason, amount_difference, Evidence(fields, amount_difference, date_difference, rule, reason, duplicates)


def deterministic_score(evidence: Evidence) -> tuple[Decimal, list[dict]]:
    weights = {"reference": Decimal("30"), "amount": Decimal("30"), "merchant": Decimal("15"), "currency": Decimal("10"), "date": Decimal("10")}
    factors = []
    score = Decimal("0")
    for field in evidence.fields:
        points = weights.get(field["field"], Decimal("0")) if field["status"] == "MATCH" else Decimal("0")
        score += points
        factors.append({"name": field["field"].replace("_", " ").title(), "points": str(points), "status": field["status"]})
    if evidence.duplicate_signals:
        score = max(Decimal("0"), score - Decimal("35"))
        factors.append({"name": "Duplicate signal", "points": "-35", "status": "MISMATCH"})
    return (score / Decimal("100")).quantize(Decimal("0.0001")), factors
