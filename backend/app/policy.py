from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Policy:
    auto_resolve_threshold: Decimal = Decimal("0.95")
    review_threshold: Decimal = Decimal("0.70")
    high_risk_threshold: Decimal = Decimal("0.45")
    high_value_threshold: Decimal = Decimal("50000")


def decide(score: Decimal, amount: Decimal, has_duplicate: bool, matched: bool, policy: Policy) -> tuple[str, str]:
    if has_duplicate or score < policy.high_risk_threshold:
        return "HIGH_RISK", "Duplicate or low-confidence evidence requires escalation"
    if amount >= policy.high_value_threshold:
        return "HUMAN_REVIEW", "High-value transaction requires manager control"
    if matched and score >= policy.auto_resolve_threshold:
        return "AUTO_RESOLVE", "Deterministic evidence exceeds auto-resolution threshold"
    if score >= policy.review_threshold:
        return "POLICY_REVIEW", "Evidence is sufficient for controlled review"
    return "HUMAN_REVIEW", "Evidence is ambiguous and requires human verification"
