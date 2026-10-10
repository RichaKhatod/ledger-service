# Double-Entry Payments Ledger (with Autonomous-Agent Spending Guardrails)

A production-shaped double-entry payments ledger built in Django / DRF / PostgreSQL — with a second layer, an autonomous-agent spending-control system, built on top of it.

The project is two layers:

1. **The ledger (the main project)** — a double-entry accounting core where every movement of money is a balanced, immutable transaction, with correctness enforced at the database level. It handles balanced transactions, idempotent requests, concurrency-safe payments, reversals, an audit trail, signed webhooks, and reconciliation against provider records.
2. **The guardrails (built on the ledger)** — a policy engine and budget-enforcement system that prevents AI agents from making unauthorized or excessive financial transactions. It uses the ledger as its money layer: every approved agent spend becomes balanced ledger entries.

The dependency runs one way — the guardrails depend on the ledger; the ledger stands alone.

---

## Part 1 — The Ledger (Base Layer)

Every movement of money is a `Transaction` with two or more `Entry` rows that **must sum to zero**. A positive amount is a debit and a negative amount is a credit. Amounts are integers in the smallest currency unit, and the default currency is INR.

- **`create_transaction()`** (`ledger/utils.py`) — validates that the entries balance, writes the transaction and its entries atomically, and records a `LedgerAuditEvent`
- **Wallet top-up** — debits *PSP Receivable* and credits the user's wallet account
- **Wallet payment** — locks the wallet with `SELECT FOR UPDATE`, checks the balance, then debits the wallet and credits *Merchant Payable* (internal helper, no endpoint yet)
- **Reversals** — `reverse_transaction()` writes mirror-image entries as a `refund` pointing at the original. Entries are never edited.
- **Idempotency** — `POST /ledger/transactions/` requires an `Idempotency-Key` header. The payload is hashed (canonical JSON + SHA-256).
  - same key + same payload → the stored response is returned with `200`
  - same key + different payload → `409`
- **Signed webhooks** — `POST /ledger/webhooks/payment/` verifies three things:
  - an HMAC-SHA256 signature over `"{timestamp}.{body}"` (compared in constant time)
  - a timestamp within ±5 minutes
  - a unique nonce (`WebhookNonce`), which blocks replays
- **Reconciliation** — the hourly `reconcile` Celery task compares `ProviderRecord` rows (the provider's view) with ledger top-ups. It records each `ReconciliationMismatch` as `missing_in_ledger`, `missing_in_provider` or `amount_mismatch`.
- **Structured logging** — the `ledger` logger emits JSON via `python-json-logger`

### Database-Level Guarantees

PostgreSQL enforces the ledger invariants a second time, so neither an application bug nor manual SQL can break them:

| Migration | Guarantee |
|---|---|
| `ledger/0001` | `CHECK (amount <> 0)` on entries |
| `ledger/0002` | Deferred constraint trigger: each transaction's entries must sum to zero at commit |
| `ledger/0003` | `ledger_entry` rejects `UPDATE` / `DELETE` (append-only) |
| `ledger/0006` | `ledger_ledgerauditevent` rejects `UPDATE` / `DELETE` (append-only) |

These triggers are why the project requires PostgreSQL. SQLite won't work.

---

## Part 2 — The Guardrails (Built on the Ledger)

### The Problem

An AI agent with access to company funds receives a prompt injection and attempts a large unauthorized purchase. Without guardrails, the money is gone before anyone notices.

### The Solution

A deterministic, non-promptable middleware layer between the agent's intent and actual money movement. The agent can *request* a spend — it can never *execute* one. Every approved spend flows into the ledger as balanced entries.

```
Agent (LLM) ──► POST /policy/process_spend_request/
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

### Key Design Principles

- **Separation of concerns** — the LLM agent never touches money. The policy engine is deterministic and testable. The ledger holds the actual value.
- **Defense in depth** — per-transaction limits, daily/monthly budgets, vendor allowlists, velocity detection, and human-in-the-loop approval all work together.
- **Blast radius containment** — hard caps at multiple layers ensure a single compromise can't drain the account.
- **Auditability** — every action (approve, reject, escalate, freeze) creates an immutable audit event.

### How a Spend Request Flows

1. Agent authenticates via `X-Agent-Key` header (SHA-256 hashed, never stored raw)
2. Agent submits `POST /policy/process_spend_request/` with amount + vendor
3. Policy engine evaluates against budget rules (pure function, no DB access)
4. Velocity checks scan for anomalous patterns (DB queries, separate from engine)
5. Decision: **APPROVE** (deduct budget + create ledger entries), **REJECT** (403, no budget impact), or **ESCALATE** (create ApprovalRequest for human)
6. Audit event logged for every outcome
7. If escalated: human hits `POST /policy/process_approval_decision/<id>/decide/` to approve or deny (approvals expire after 30 minutes)

### Anomaly Detection

Velocity checks run before approval and catch:
- **Velocity spike** — approved spending in the last hour plus the new request exceeds 3x the daily limit
- **High single transaction** — single request > 50% of daily limit
- **New vendor + high amount** — first transaction with an unknown vendor above 25% of the auto-approve threshold

Any hit creates an `AnomalyAlert` and upgrades the request to **ESCALATE**, even if the policy engine would have approved it.

A Celery periodic task scans every 15 minutes for rapid spending patterns across all agents (flags a `rapid_spending` alert when an agent's approved spend in the last 15 minutes exceeds 80% of its daily limit).

---

## Architecture

### Apps

| App | Layer | Purpose |
|---|---|---|
| `ledger` | Base | Double-entry accounting — balanced transactions, idempotency keys, concurrency-safe payments, reversals, signed payment webhooks, reconciliation |
| `agents` | Guardrails | Agent identity, API key authentication, kill switch |
| `budgets` | Guardrails | Budget envelopes with hard spending limits |
| `policy` | Guardrails | Spend request processing, policy engine, approval workflow |
| `audit` | Guardrails | Append-only audit event log, anomaly alerts |
| `config` | Shared | Django project settings, URL routing, Celery app, DRF exception handler, OpenAPI docs |

### Concurrency Safety

Both wallet payments (ledger) and budget deductions (guardrails) use `SELECT FOR UPDATE` inside `transaction.atomic()` — two simultaneous requests cannot overdraft. The row-level lock serializes access so only one request proceeds at a time. This is verified by a test that fires concurrent debits at a single wallet and asserts no double-spend.

### Background Jobs (Celery Beat)

| Task | Interval | What it does |
|---|---|---|
| `policy.tasks.expire_pending_approvals` | 60 s | Denies approvals past `expires_at`, marks spend request `expired` |
| `policy.tasks.scan_for_anomalies` | 15 min | Raises `rapid_spending` alerts |
| `ledger.tasks.reconcile` | 1 h | Ledger ↔ provider reconciliation |

---

## Tech Stack

- **Python 3.12 / Django 5.2 / DRF** — API layer
- **PostgreSQL 16** — ACID transactions and database-enforced ledger invariants (triggers)
- **Celery + Redis** — approval expiry, anomaly scanning, ledger reconciliation periodic tasks
- **drf-spectacular** — OpenAPI schema, Swagger UI, ReDoc
- **python-json-logger** — structured JSON logs
- **Docker Compose** — containerized development (web, db, redis, celery_worker, celery_beat)
- **pytest** — unit, integration, and end-to-end tests

---

## Setup

### Prerequisites

- Docker and Docker Compose

### Run

```bash
git clone https://github.com/RichaKhatod/ledger-service.git
cd ledger-service
cp .env.example .env  # configure DB credentials (see Environment Variables below)
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web pytest -v  # run all tests
```

Once running, interactive API docs are at:

| URL | What |
|---|---|
| `http://localhost:8000/api/docs/` | Swagger UI |
| `http://localhost:8000/api/redoc/` | ReDoc |
| `http://localhost:8000/api/schema/` | Raw OpenAPI schema |
| `http://localhost:8000/admin/` | Django admin |

### Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key (required, the app won't start without it) |
| `DEBUG` | `True` to enable debug mode |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Postgres credentials (also used by the `db` container) |
| `DB_HOST`, `DB_PORT` | Use `db` / `5432` inside Docker Compose |
| `WEBHOOK_SECRET` | HMAC key for `/ledger/webhooks/payment/` (needed by the webhook tests too) |

Notes:
- `CELERY_BROKER_URL` is hard-coded to `redis://redis:6379/0`.
- Redis is exposed on host port **6380**.
- DRF throttling is set in `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`.

### Seed Test Data

```bash
docker compose exec web python manage.py seed
```

Creates the system ledger accounts: *Company Bank*, *PSP Receivable*, *Fee Revenue*, *Merchant Payable*, *Held Funds*.

The guardrail flow writes to two more accounts, **Agent Expense** (`expense`) and **Vendor Payable** (`liability`). Create them via `POST /ledger/accounts/` or the admin. If they are missing, approved spends still deduct the budget but skip the ledger entry.

Agents are created via `POST /agents/create_with_key/`. Budget envelopes are currently created through the admin or the Django shell.

---

## API Reference

### Ledger

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/ledger/health_point_check/` | None | Health check |
| GET / POST | `/ledger/accounts/` | None | List or create accounts (`name, type, purpose, user_id, currency`) |
| GET | `/ledger/accounts/<id>/balance/` | None | Account balance (sum of entries) |
| POST | `/ledger/transactions/` | `Idempotency-Key` header | Wallet top-up (`user_id, amount`). Returns `201` new, `200` replay, `409` key reused with a different payload |
| POST | `/ledger/webhooks/payment/` | `X-Signature`, `X-Timestamp`, `X-Nonce` | Signed provider webhook that triggers a wallet top-up |

Webhook signature: `X-Signature = hex(HMAC_SHA256(WEBHOOK_SECRET, f"{X-Timestamp}.{raw_body}"))`. `X-Timestamp` is in Unix seconds.

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

**Response codes:**
- **Spend requests:** `201` approved, `202` escalated, `403` rejected, `401` missing or invalid agent key
- **Approval decisions:** `200` done, `403` budget exhausted since escalation, `409` already decided, `410` expired

All DRF errors are wrapped by `config/exception_handler.py` as `{"error": {"status_code": ..., "detail": ...}}`.

> **Note:** "Admin" marks endpoints intended for operators. A permission class is not yet enforced on them. See [Known Limitations](#known-limitations).

---

## Data Model

Ledger:

```
Account                  name, type, purpose, user_id, currency
Transaction              kind, idempotency_key, reverses (FK → self), metadata
  └── Entry (1:N)        account (FK), amount (≠ 0), currency          ← immutable
IdempotencyKey           key (unique), request_hash, response_body, transaction
LedgerAuditEvent         event_type, transaction, payload              ← immutable
WebhookNonce             nonce (unique)
ProviderRecord           provider_ref (unique), amount, status, transaction
ReconciliationMismatch   mismatch_type, provider_ref, transaction, ledger_amount, provider_amount
```

Guardrails:

```
Agent
  ├── name, api_key_hash (SHA-256), is_active, created_at
  │
  ├── BudgetEnvelope (1:1)
  │     ├── daily_limit, monthly_limit, per_txn_limit
  │     ├── auto_approve_threshold
  │     ├── spent_today, spent_this_month
  │     ├── vendor_allowlist (JSONField), currency
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

Every foreign key uses `on_delete=PROTECT`, so no financial record can be removed by a cascade.

---

## Tests

Tests span both layers, covering:

- **Ledger** — account CRUD, balanced and unbalanced transactions, entry immutability, balances, idempotency (first / retry / conflict), no double-spend under concurrency, webhook signature / stale timestamp / replay, reconciliation mismatches
- **Agent auth** — key hashing, auth success/failure, frozen agent rejection
- **Budget CRUD** — GET, PATCH, spending summary
- **Policy engine** — approve within limits, reject over per-txn/daily/monthly, reject unknown vendor, escalate above threshold
- **Approval workflow** — approve/deny escalated requests, already-decided (409), expired (410)
- **Audit logging** — events created on approve/reject/escalate
- **Anomaly detection** — high single transaction, new vendor + high amount
- **E2E flows** — full happy path, escalation → human approval, prompt injection blocked, concurrent requests don't overdraft

```bash
docker compose exec web pytest ledger/tests.py -v                                                            # ledger
docker compose exec web pytest agents/tests.py budgets/tests.py policy/tests.py audit/tests.py tests_e2e.py -v   # guardrails
```

Tests need a running Postgres (for the triggers) and `WEBHOOK_SECRET` set.

---

## Design Decisions

### Why enforce ledger invariants in the database?

The application already checks that entries balance. The Postgres triggers check again at commit time and block edits to entries and ledger audit events. A bug in a new code path, a bad migration, or someone in `psql` cannot quietly unbalance the books or rewrite history. Corrections must be made as reversing transactions. Correctness is guaranteed at the database, not merely in application code.

### Why a deferred constraint trigger for the balance check?

A transaction's entries are inserted one row at a time, so after the first insert the entries don't yet sum to zero. A deferred constraint trigger validates at **commit** rather than per-row, so the "entries sum to zero" invariant is checked once the whole transaction is assembled — which is the only point at which it should hold.

### Why derive balances instead of storing them?

An account's balance is computed as `SUM(entries)` on demand, never stored in a column. A stored balance can drift from the entries that produced it and needs careful locking on every update. Deriving it from immutable entries means it is always correct by construction.

### Why idempotency keys?

A client whose request succeeds but whose response is lost will retry. Without protection, the retry processes the payment twice. The key + request-hash + cached-response design returns the original result on a genuine retry and returns `409` when a key is reused with a different payload — so money moves exactly once.

### Why SELECT FOR UPDATE?

Without it, two simultaneous requests could both read the same balance, both pass the "sufficient funds" check, and both debit — a double-spend. The row-level lock ensures only one transaction proceeds at a time. The same pattern guards budget deductions in the guardrails layer.

### Why a pure policy engine?

The `evaluate()` function in `policy/engine.py` takes amount, vendor, and envelope as inputs and returns a decision. No DB calls, no side effects. This means unit tests run instantly without a database, the function is deterministic, and a prompt injection cannot influence the evaluation — it only ever sees structured data, never raw prompts.

### Why tiered authorization?

Not all spends are equal. A small routine spend doesn't need the same scrutiny as a large vendor payment. The auto-approve threshold separates routine spends from ones that need human review — the same idea as transaction limits on a payment card.

### Why double-entry for agent spends?

Every approved spend creates balanced ledger entries (debit Agent Expense, credit Vendor Payable). The books always balance, so any discrepancy is detectable, and spend history is fully reconstructable from the ledger alone.

---

## Interview Talking Points

- **Database-enforced correctness** — double-entry balance and append-only immutability enforced by Postgres triggers, not just application code
- **Deferred constraint trigger** — validates the sum-to-zero invariant at commit, because entries insert one at a time
- **Concurrency control** — `SELECT FOR UPDATE` prevents double-spend under concurrent requests, proven by a concurrent-debit test
- **Idempotency** — key + request-hash + cached response; retries return the original, mismatched payloads return 409
- **Webhook security** — HMAC with constant-time comparison (timing-attack safe), timestamp window, and nonce replay protection
- **Reconciliation** — scheduled job diffing the internal ledger against provider records
- **Immutability / event sourcing** — ledger entries and audit events are append-only; state is reconstructable from history
- **Separation of concerns** — the LLM agent never touches money; the policy engine is deterministic, testable, and non-promptable
- **Layered architecture** — a reusable ledger foundation with an independent guardrails system built on top of it

---

## Known Limitations

- **Admin endpoints are unauthenticated.** Budget, approval, freeze and audit endpoints still use DRF's default `AllowAny` permission. They need an admin permission class.
- **Budget counters never reset.** `last_daily_reset` and `last_monthly_reset` exist, but no task resets `spent_today` or `spent_this_month` yet.
- **No API to create a `BudgetEnvelope`.** Use the admin or the shell.
- **`seed` doesn't create *Agent Expense* or *Vendor Payable*.**
- **Spend requests aren't idempotent yet.** `SpendRequest.idempotency_key` exists but isn't checked.
- **Nothing populates `ProviderRecord` yet,** so reconciliation has no provider data to compare against.
- **`audit.AuditEvent` isn't trigger-protected.** Unlike `LedgerAuditEvent`, it is append-only by convention only.
- **`wallet_payment` and `reverse_transaction` have no endpoints.**
- **`ALLOWED_HOSTS` is empty.** Set it before deploying with `DEBUG=False`.