# Financial Guardrails for Autonomous AI Agents

A policy engine and budget enforcement system that prevents AI agents from making unauthorized or excessive financial transactions. Built on top of a double-entry payments ledger.

## The Problem

An AI agent with access to company credit cards receives a prompt injection and attempts a $50,000 purchase of unnecessary services. Without guardrails, the money is gone before anyone notices.

## The Solution

A deterministic, non-promptable middleware layer between the agent's intent and actual money movement. The agent can *request* a spend — it can never *execute* one.

```
Agent (LLM) ──► POST /policy/spend-requests/
                        │
                  ┌──────▼──────┐
                  │ Policy Engine │◄── Budget rules, velocity checks
                  └──────┬──────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
        APPROVE      ESCALATE      REJECT
            │            │            │
            ▼            │            ▼
  Ledger entries         │        403 response
  Budget deducted        ▼
                  ApprovalRequest
                  (human decides)
                         │
                         ▼
                  ┌─────────────────┐
                  │  Audit Event Log │  (append-only)
                  └─────────────────┘
```

## Key Design Principles

- **Separation of concerns** — the LLM agent never touches money. The policy engine is deterministic and testable. The payment layer holds credentials.
- **Defense in depth** — per-transaction limits, daily/monthly budgets, vendor allowlists, velocity detection, and human-in-the-loop approval all work together.
- **Blast radius containment** — hard caps at multiple layers ensure a single compromise can't drain the account.
- **Auditability** — every action (approve, reject, escalate, freeze) creates an immutable audit event.

## Architecture

### Apps

| App | Purpose |
|---|---|
| `agents` | Agent identity, API key authentication, kill switch |
| `budgets` | Budget envelopes with hard spending limits |
| `policy` | Spend request processing, policy engine, approval workflow |
| `audit` | Append-only audit event log, anomaly alerts |
| `ledger` | Double-entry accounting (base project) |

### How a Spend Request Flows

1. Agent authenticates via `X-Agent-Key` header (SHA-256 hashed, never stored raw)
2. Agent submits `POST /policy/process_spend_request/` with amount + vendor
3. Policy engine evaluates against budget rules (pure function, no DB access)
4. Velocity checks scan for anomalous patterns (DB queries, separate from engine)
5. Decision: **APPROVE** (deduct budget + create ledger entries), **REJECT** (403, no budget impact), or **ESCALATE** (create ApprovalRequest for human)
6. Audit event logged for every outcome
7. If escalated: human hits `POST /policy/approvals/<id>/decide/` to approve or deny

### Concurrency Safety

Budget deductions use `SELECT FOR UPDATE` inside `transaction.atomic()` — two simultaneous requests cannot overdraft the budget. Same pattern used in payment capture flows at companies like Razorpay.

### Anomaly Detection

Velocity checks run before approval and catch:
- **Velocity spike** — spending in the last hour exceeds 3x the agent's hourly average
- **High single transaction** — single request > 50% of daily limit
- **New vendor + high amount** — first transaction with an unknown vendor above a threshold

A Celery periodic task scans every 15 minutes for rapid spending patterns across all agents.

## Tech Stack

- **Python 3.12 / Django 5.2 / DRF** — API layer
- **PostgreSQL 16** — ACID transactions for budget enforcement
- **Celery + Redis** — approval expiry, anomaly scanning periodic tasks
- **Docker Compose** — containerized development (web, db, redis)
- **pytest** — 32 tests (unit, integration, end-to-end)

## Setup

### Prerequisites

- Docker and Docker Compose

### Run

```bash
git clone https://github.com/RichaKhatod/ledger-service.git
cd ledger-service
cp .env.example .env  # configure DB credentials
docker compose up -d
docker-compose exec web python manage.py migrate
docker-compose exec web pytest -v  # run all tests
```

### Seed Test Data

```bash
docker-compose exec web python manage.py seed_guardrails
```

Creates a test agent with API key, budget envelope, and ledger accounts.

## API Reference

### Agent Management

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/agents/create_with_key/` | None | Create agent, returns raw API key (shown once) |
| POST | `/agents/freeze_agent/<id>/` | Admin | Kill switch — freezes agent, auto-denies pending approvals |
| POST | `/agents/unfreeze_agent/<id>/` | Admin | Reactivate frozen agent |

### Budget Management

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/budgets/get_budget/<agent_id>/` | Admin | View budget state (limits, spent, remaining) |
| PATCH | `/budgets/update_budget/<agent_id>/` | Admin | Update limits (daily, monthly, per-txn, threshold, vendor allowlist) |
| GET | `/budgets/get_spend_summary/<agent_id>/` | Admin | Spending breakdown by vendor and by day |

### Policy Engine

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/policy/process_spend_request/` | Agent key | Submit a spend request — returns approve/reject/escalate |
| POST | `/policy/process_approval_decision/<id>/decide/` | Admin | Approve or deny an escalated request |

### Audit

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/audit/get_anomaly_alerts/` | Admin | List anomaly alerts, filterable by agent_id |

## Data Model

```
Agent
  ├── name, api_key_hash (SHA-256), is_active, created_at
  │
  ├── BudgetEnvelope (1:1)
  │     ├── daily_limit, monthly_limit, per_txn_limit
  │     ├── auto_approve_threshold
  │     ├── spent_today, spent_this_month
  │     ├── vendor_allowlist (JSONField)
  │     └── last_daily_reset, last_monthly_reset
  │
  ├── SpendRequest (1:N)
  │     ├── amount, vendor, purpose, status
  │     ├── policy_decision_reason
  │     ├── transaction (FK → ledger.Transaction)
  │     └── ApprovalRequest (1:1, if escalated)
  │           ├── approver_name, decision, decided_at, expires_at
  │
  ├── AuditEvent (1:N)
  │     ├── event_type, payload (JSONField), created_at
  │
  └── AnomalyAlert (1:N)
        ├── alert_type, details (JSONField), resolved, created_at
```

## Tests

32 tests across 5 files covering:

- **Agent auth** — key hashing, auth success/failure, frozen agent rejection
- **Budget CRUD** — GET, PATCH, spending summary
- **Policy engine** — approve within limits, reject over per-txn/daily/monthly, reject unknown vendor, escalate above threshold
- **Approval workflow** — approve/deny escalated requests, already-decided (409), expired (410)
- **Audit logging** — events created on approve/reject/escalate
- **Anomaly detection** — high single transaction, new vendor + high amount
- **E2E flows** — full happy path, escalation → human approval, prompt injection blocked, concurrent requests don't overdraft

```bash
docker-compose exec web pytest agents/tests.py budgets/tests.py policy/tests.py audit/tests.py tests_e2e.py -v
```

## Design Decisions

### Why a pure policy engine?

The `evaluate()` function in `policy/engine.py` takes amount, vendor, and envelope as inputs and returns a decision. No DB calls, no side effects. This means:
- Unit tests run instantly without a database
- The function is deterministic — same inputs always produce the same output
- A prompt injection cannot influence the evaluation — it only sees structured data, never raw prompts

### Why SELECT FOR UPDATE?

Without it, two simultaneous requests could both read `spent_today=90_000` with a `daily_limit=100_000`, both approve a 15_000 spend, and overdraft to 120_000. The row-level lock ensures only one transaction proceeds at a time.

### Why double-entry ledger integration?

Every approved spend creates balanced ledger entries (debit Agent Expense, credit Vendor Payable). This means:
- The books always balance — any discrepancy is detectable
- Spend history is reconstructable from the ledger alone
- The pattern maps directly to how companies like Razorpay and Cashfree handle payment capture internally

### Why tiered authorization?

Not all spends are equal. A ₹100 API call doesn't need the same scrutiny as a ₹50,000 vendor payment. The auto-approve threshold separates routine spends from ones that need human review — same concept as credit card transaction limits.

## Interview Talking Points

- **Concurrency control** — `SELECT FOR UPDATE` prevents budget overdraft under concurrent agent requests
- **Idempotency** — reuses existing IdempotencyKey system from the ledger
- **Immutability** — audit events and ledger entries are append-only
- **Separation of concerns** — LLM agent never touches money; policy engine is deterministic, testable, non-promptable
- **Blast radius** — hard caps at per-txn, daily, monthly, and virtual card layers
- **Event sourcing pattern** — audit log can reconstruct full state at any point in time
- **Rate limiting for money** — same algorithm as API rate limits, different resource