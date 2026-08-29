import csv
import io
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, settings
from .models import (AuditLog, BankTransaction, Batch, ExceptionRecord, GroundTruth,
                     Order, Payment, ReconciliationResult, Rejection, Settlement, id_for,
                     now_utc)
from .schemas import BatchResponse, DemoRequest, ReviewRequest, UploadResponse

Base.metadata.create_all(engine)
app = FastAPI(title="AI Finance Controller", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def audit(db: Session, batch_id: str, entity_type: str, entity_id: str, action: str, reason: str, metadata: dict | None = None):
    db.add(AuditLog(id=id_for("AUD"), batch_id=batch_id, entity_type=entity_type, entity_id=entity_id,
                    action=action, actor="system", reason=reason, metadata_json=metadata or {}))


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reconcile(db: Session, batch_id: str) -> None:
    payments = db.scalars(select(Payment).where(Payment.batch_id == batch_id)).all()
    settlements = {item.transaction_id: item for item in db.scalars(select(Settlement).where(Settlement.batch_id == batch_id)).all()}
    banks = db.scalars(select(BankTransaction).where(BankTransaction.batch_id == batch_id)).all()
    used_banks: set[str] = set()
    for payment in payments:
        settlement = settlements.get(payment.id)
        bank = next((b for b in banks if b.id not in used_banks and b.reference == payment.id), None)
        if bank is None and settlement:
            bank = next((b for b in banks if b.id not in used_banks and b.amount == settlement.net_amount
                         and b.merchant_id == payment.merchant_id
                         and abs((b.transaction_date - settlement.settlement_date).days) <= 1), None)
        confidence = Decimal("0")
        status = "UNMATCHED"
        match_type = "NO_MATCH"
        reason = "No settlement or bank transaction was found"
        if settlement and bank:
            used_banks.add(bank.id)
            amount_delta = abs(payment.amount - settlement.net_amount)
            date_delta = abs((bank.transaction_date - payment.payment_date).days)
            if settlement.gross_amount == payment.amount and amount_delta == 0 and bank.amount == settlement.net_amount and date_delta <= 2:
                confidence, status, match_type = Decimal("0.99"), "MATCHED", "EXACT_CHAIN"
                reason = "Payment, settlement and bank amount agree"
            elif settlement.gross_amount == payment.amount and bank.amount == settlement.net_amount and date_delta <= 2:
                confidence, status, match_type = Decimal("0.96"), "MATCHED", "FEE_ADJUSTED"
                reason = "Net settlement agrees after gateway fee and tax"
            elif bank.merchant_id == payment.merchant_id and date_delta <= 2:
                confidence, status, match_type = Decimal("0.82"), "PENDING_REVIEW", "RULE_BASED"
                reason = "Merchant and date align, but financial amounts need review"
            else:
                confidence, match_type = Decimal("0.42"), "AI_ASSISTED"
                reason = "Conflicting evidence requires human verification"
        result = ReconciliationResult(id=id_for("REC"), batch_id=batch_id, payment_id=payment.id,
                                      bank_transaction_id=bank.id if bank else None, match_type=match_type,
                                      confidence=confidence, status=status, reason=reason)
        db.add(result)
        if status != "MATCHED":
            exception_type = "MISSING_TRANSACTION" if not settlement or not bank else "AMOUNT_MISMATCH"
            db.flush()
            db.add(ExceptionRecord(id=id_for("EXC"), batch_id=batch_id, reconciliation_id=result.id,
                                   exception_type=exception_type, severity="HIGH" if confidence < Decimal("0.75") else "MEDIUM",
                                   ai_reason=reason, ai_confidence=confidence, evidence={
                                       "payment_id": payment.id, "payment_amount": str(payment.amount),
                                       "settlement_amount": str(settlement.net_amount) if settlement else None,
                                       "bank_amount": str(bank.amount) if bank else None,
                                   }))
        audit(db, batch_id, "payment", payment.id, "RECONCILED", reason, {"status": status, "confidence": str(confidence)})
    db.query(Batch).filter(Batch.id == batch_id).update({"status": "COMPLETED"})
    db.commit()


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/demo/generate", response_model=BatchResponse)
def generate_demo(request: DemoRequest, db: Session = Depends(get_db)):
    rng = random.Random(request.seed)
    batch = Batch(id=id_for("BAT"), name=f"Demo batch · {request.records:,} records", status="PROCESSING")
    db.add(batch)
    start = date(2026, 8, 1)
    for index in range(request.records):
        suffix = batch.id[-6:].upper()
        payment_id, order_id, merchant = f"PAY-{suffix}-{index + 1:05}", f"ORD-{suffix}-{index + 1:05}", "M-001"
        amount = Decimal(rng.choice(["499.00", "1299.00", "2500.00", "10000.00"]))
        day = start + timedelta(days=rng.randrange(20))
        fee, tax = cents(amount * Decimal("0.018")), cents(amount * Decimal("0.018") * Decimal("0.18"))
        net = cents(amount - fee - tax)
        anomalous = rng.random() < request.anomaly_rate
        anomaly = rng.choice(["missing", "amount", "date"]) if anomalous else "clean"
        db.add(Order(id=order_id, batch_id=batch.id, merchant_id=merchant, customer_id=f"C-{suffix}-{index+1:05}", order_value=amount, order_date=day))
        db.add(Payment(id=payment_id, batch_id=batch.id, order_id=order_id, merchant_id=merchant, payment_mode=rng.choice(["UPI", "CARD", "NETBANKING"]), amount=amount, payment_date=day))
        db.add(Settlement(id=f"SET-{suffix}-{index+1:05}", batch_id=batch.id, transaction_id=payment_id, merchant_id=merchant, gross_amount=amount, gateway_fee=fee, tax_amount=tax, net_amount=net, settlement_date=day + timedelta(days=1)))
        bank_amount = net + (Decimal("37.00") if anomaly == "amount" else Decimal("0"))
        if anomaly != "missing":
            db.add(BankTransaction(id=f"BANK-{suffix}-{index+1:05}", batch_id=batch.id, merchant_id=merchant, amount=bank_amount, transaction_date=day + timedelta(days=3 if anomaly == "date" else 1), reference=payment_id, narration="ABC STORE settlement", bank_name="HDFC Bank"))
        db.add(GroundTruth(batch_id=batch.id, payment_id=payment_id, should_match=anomaly == "clean", expected_reason=anomaly))
    db.commit()
    reconcile(db, batch.id)
    return batch


@app.get("/api/v1/batches", response_model=list[BatchResponse])
def batches(db: Session = Depends(get_db)):
    return db.scalars(select(Batch).order_by(Batch.created_at.desc())).all()


@app.get("/api/v1/batches/{batch_id}/summary")
def summary(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    total = db.scalar(select(func.count()).select_from(ReconciliationResult).where(ReconciliationResult.batch_id == batch_id)) or 0
    matched = db.scalar(select(func.count()).select_from(ReconciliationResult).where(ReconciliationResult.batch_id == batch_id, ReconciliationResult.status == "MATCHED")) or 0
    open_exceptions = db.scalar(select(func.count()).select_from(ExceptionRecord).where(ExceptionRecord.batch_id == batch_id, ExceptionRecord.status == "PENDING_REVIEW")) or 0
    resolved = db.scalar(select(func.count()).select_from(ExceptionRecord).where(ExceptionRecord.batch_id == batch_id, ExceptionRecord.status != "PENDING_REVIEW")) or 0
    predictions = {item.payment_id: item.status == "MATCHED" for item in db.scalars(select(ReconciliationResult).where(ReconciliationResult.batch_id == batch_id)).all()}
    truth = db.scalars(select(GroundTruth).where(GroundTruth.batch_id == batch_id)).all()
    correct = sum(predictions.get(item.payment_id) == item.should_match for item in truth)
    return {"batch": BatchResponse.model_validate(batch, from_attributes=True), "total_records": total, "matched_records": matched,
            "exceptions": total - matched, "open_exceptions": open_exceptions, "resolved_exceptions": resolved,
            "match_rate": round(matched / total * 100, 1) if total else 0,
            "resolution_rate": round((matched + resolved) / total * 100, 1) if total else 0,
            "accuracy": round(correct / len(truth) * 100, 1) if truth else None}


@app.get("/api/v1/batches/{batch_id}/exceptions")
def exceptions(batch_id: str, db: Session = Depends(get_db)):
    return db.scalars(select(ExceptionRecord).where(ExceptionRecord.batch_id == batch_id).order_by(ExceptionRecord.created_at.desc())).all()


@app.post("/api/v1/exceptions/{exception_id}/review")
def review(exception_id: str, request: ReviewRequest, db: Session = Depends(get_db)):
    exception = db.get(ExceptionRecord, exception_id)
    if not exception:
        raise HTTPException(404, "Exception not found")
    exception.status = "APPROVED" if request.decision == "APPROVE" else "REJECTED"
    exception.reviewer_comment = request.comment
    exception.resolved_at = now_utc()
    result = db.get(ReconciliationResult, exception.reconciliation_id)
    result.status = "MATCHED" if request.decision == "APPROVE" else "UNMATCHED"
    audit(db, exception.batch_id, "exception", exception.id, f"HUMAN_{request.decision}", request.comment)
    db.commit()
    return {"status": exception.status, "exception_id": exception.id}


@app.post("/api/v1/batches/{batch_id}/upload", response_model=UploadResponse)
async def upload(batch_id: str, source_type: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not db.get(Batch, batch_id):
        raise HTTPException(404, "Batch not found")
    required = {"payments": {"transaction_id", "order_id", "merchant_id", "amount", "payment_date"}, "bank": {"bank_txn_id", "merchant_id", "amount", "transaction_date", "reference"}}
    if source_type not in required:
        raise HTTPException(400, "source_type must be payments or bank")
    rows = list(csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig"))))
    accepted = 0
    for row_number, row in enumerate(rows, start=2):
        try:
            missing = required[source_type] - row.keys()
            if missing:
                raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
            if source_type == "payments":
                db.add(Payment(id=row["transaction_id"], batch_id=batch_id, order_id=row["order_id"], merchant_id=row["merchant_id"], payment_mode=row.get("payment_mode", "UNKNOWN"), amount=Decimal(row["amount"]), payment_date=date.fromisoformat(row["payment_date"])))
            else:
                db.add(BankTransaction(id=row["bank_txn_id"], batch_id=batch_id, merchant_id=row["merchant_id"], amount=Decimal(row["amount"]), transaction_date=date.fromisoformat(row["transaction_date"]), reference=row["reference"], narration=row.get("narration"), bank_name=row.get("bank_name")))
            accepted += 1
        except (ValueError, KeyError) as error:
            db.add(Rejection(batch_id=batch_id, source_type=source_type, row_number=row_number, reason=str(error), raw_record=row))
    db.commit()
    audit(db, batch_id, source_type, file.filename or "upload", "INGESTED", f"Accepted {accepted} rows")
    db.commit()
    return UploadResponse(batch_id=batch_id, source_type=source_type, accepted=accepted, rejected=len(rows) - accepted)
