# AI Finance Controller

A finance operations control room for reconciling payment events, gateway settlements, and bank credits. The first vertical slice follows the architecture principle: deterministic matching first, policy-gated uncertainty second, human review for the remainder.

## Run locally

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Use **Generate demo batch** to create labeled synthetic records and populate the control room.

## What is included

- Demo data generator with clean records and missing, amount, and date anomalies
- SQLite by default for zero-setup local development; PostgreSQL is supported through `DATABASE_URL`
- CSV ingestion with required-column, amount, and date validation plus persisted rejection rows
- Exact chain, fee-adjusted, and rule-based reconciliation levels
- Exception queue with evidence snapshots and approve/reject writeback
- Audit events for ingestion, reconciliation, and human decisions
- Responsive dashboard with batch switching and operational metrics

## Next production boundaries

The API is intentionally a modular monolith for the first build. Add a task queue around `reconcile`, provider-backed structured AI analysis for the low-confidence branch, authentication/RBAC, migrations, and a real metrics exporter once the domain behavior is validated.
