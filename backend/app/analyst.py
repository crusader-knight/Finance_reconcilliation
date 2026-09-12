from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class AnalystResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: str
    confidence: Decimal = Field(ge=0, le=1)
    risk_level: str
    likely_cause: str
    recommended_action: str
    explanation: str
    evidence: list[str]
    suggested_resolution: str


class ExceptionAnalyst:
    """Provider boundary. A real provider can implement analyze() without changing policy."""

    def analyze(self, evidence: dict) -> AnalystResult:
        signals = evidence.get("duplicate_signals", [])
        fields = {item.get("field"): item.get("status") for item in evidence.get("fields", [])}
        if signals:
            classification, cause = "duplicate_payment", "The same source identity or fingerprint appeared more than once"
        elif not evidence.get("settlement_amount") or not evidence.get("bank_amount"):
            classification, cause = "missing_bank_transaction", "A downstream financial record is absent"
        elif fields.get("amount") == "MISMATCH":
            classification, cause = "fee_mismatch", "The bank credit differs from the settlement net amount"
        elif fields.get("date") == "MISMATCH":
            classification, cause = "delayed_settlement", "The credit falls outside the configured date window"
        else:
            classification, cause = "unknown", "Evidence does not support a single root cause"
        confidence = Decimal("0.86") if classification != "unknown" else Decimal("0.45")
        return AnalystResult(classification=classification, confidence=confidence, risk_level="high" if confidence < Decimal("0.7") else "medium", likely_cause=cause, recommended_action="review", explanation=f"Analyst considered the deterministic field results and classified this as {classification}.", evidence=[cause], suggested_resolution="Verify source records and record a human decision")
