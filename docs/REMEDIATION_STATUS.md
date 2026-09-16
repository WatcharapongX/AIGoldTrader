# Post-Freeze Remediation Status: Batch A & Batch A.1

## Executive Summary
This document records the formal remediation status for **Correction Batch A** and **Correction Batch A.1** of the post-freeze audit findings for **AIGoldTrader**.

All confirmed audit findings assigned to Batch A (AUD-P1-001 through AUD-P1-004) and corrective findings assigned to Batch A.1 (BATCHA-P1-001 through BATCHA-P1-003, BATCHA-P2-001, BATCHA-P3-001) have been remediated, verified against PostgreSQL 18 and SQLite runtimes, and integrated into the continuous test suite. The feature freeze baseline established at `4835051b7870b293a9036a85d5c7226b1ba70af1` remains strictly governed per [FEATURE_FREEZE.md](file:///c:/AI%20Gold%20Trader/docs/FEATURE_FREEZE.md). No new trading, execution, or broker routing features were introduced.

---

## Remediated Audit Findings: Batch A

### 1. AUD-P1-001: Terminal Candidate Lifecycle Enforcement
- **Defect**: Candidates in terminal states (`INVALIDATED`, `EXPIRED`, `SUPERSEDED`) were not systematically projected from the transition ledger prior to risk evaluation or AI context assembly.
- **Root Cause**: Strategy candidates maintained an initial status on the primary row while subsequent status changes were logged into `candidate_transitions`. Inquiries directly reading candidate rows without transition projection could evaluate or recommend stale/invalid candidates.
- **Remediation**:
  - Implemented `resolve_candidate_current_lifecycle()` in `backend/app/services/strategy/lifecycle.py`, projecting the authoritative lifecycle status from both `candidate.status` and `CandidateTransitionRecord` transitions.
  - In `backend/app/services/risk/engine.py`: Added explicit terminal state pre-check (`cand_status in {"INVALIDATED", "EXPIRED", "SUPERSEDED"}`). Any terminal candidate is immediately rejected with decision `BLOCKED`, reason `Candidate lifecycle is terminal (<STATUS>)`, and zero risk reservations created.
  - In `backend/app/services/ai/assembler.py`: Resolved candidate current lifecycle and flagged terminal candidates with `availability="UNAVAILABLE"` and descriptive unavailable reasons.
  - In `backend/app/services/risk/fingerprint.py`: Incorporated `candidate_lifecycle_status` and `candidate_transition_count` into `compute_risk_dependency_fingerprint()` to guarantee strict dependency immutability.

### 2. AUD-P1-002: Risk Evaluation Role Authorization
- **Defect**: `VIEWER` role accounts were permitted to invoke `POST /risk/evaluate`, mutating portfolio reservations and system state.
- **Root Cause**: `POST /risk/evaluate` endpoint lacked a role check, requiring only an authenticated user.
- **Remediation**:
  - In `backend/app/api/risk.py`: Added explicit role enforcement check `if user.role == Role.VIEWER: raise ForbiddenError("VIEWER role cannot execute risk evaluation")`.
  - Non-viewers (`TRADER`, `ADMIN`) are permitted subject to account ownership validation.

### 3. AUD-P1-003: Risk Decision Account Isolation & Tenant Segregation
- **Defect**: `GET /risk/decisions` and `GET /risk/decisions/{id}` did not enforce account ownership or tenant isolation, allowing users to query decisions across other accounts. Furthermore, `RiskDecisionRecord` lacked an explicit `account_id` column.
- **Root Cause**: Decisions were indexed by `account_snapshot_id` rather than directly scoped by `account_id`.
- **Remediation**:
  - In `backend/app/models/risk.py`: Added `account_id: Mapped[str]` with composite index `ix_risk_decision_account_as_of` (`account_id`, `as_of`).
  - Added migration `0013_batch_a_risk_authority` to backfill existing decision rows from `account_snapshots` and enforce `NOT NULL`.
  - In `backend/app/services/risk/repository.py`: Updated `list_recent_decisions()` to accept `account_ids: list[str] | None` and filter decisions by authorized accounts.
  - In `backend/app/api/risk.py`:
    - `GET /risk/decisions`: Non-admin users are strictly restricted to their owned accounts. Queries for unauthorized `account_id` raise `403 Forbidden`.
    - `GET /risk/decisions/{id}`: Resolves the decision and verifies `decision.account_id` belongs to the requesting user's accounts, returning `404 Not Found` on cross-tenant requests.

### 4. AUD-P1-004: Canonical Account Identity & Lock Coherence
- **Defect**: Account references accepted both account names (e.g. `"Paper Account"`) and account UUIDs, splitting `paper_account_states` rows and fracturing PostgreSQL transactional advisory locks (`pg_advisory_xact_lock`) across different hash keys for the same physical account.
- **Root Cause**: Lack of a centralized canonical account resolver allowed string name aliases to be used as primary keys in `paper_account_states` and lock keys.
- **Remediation**:
  - Created `resolve_canonical_account()` in `backend/app/services/risk/account_resolver.py`. All API entry points, background tasks, and repositories resolve input identifiers (`account_ref`) to the canonical `Account` UUID.
  - Scoped name resolution strictly to the calling tenant (`Account.name == account_ref AND Account.user_id == user.id`), preventing cross-tenant name collisions.
  - In `backend/app/services/risk/account_state.py`: Guaranteed that `paper_account_states` rows and snapshots are keyed exclusively by canonical UUID. Reconciles legacy alias rows atomically.
  - In `backend/app/api/risk.py`: Unified `pg_advisory_xact_lock` to hash exclusively the canonical account UUID (`hashtext(f"risk_account_{canonical_account_id}")`), eliminating concurrent evaluation races.

---

## Remediated Audit Findings: Batch A.1 (Corrective Scope)

### 1. BATCHA-P1-001: Safe Migration Ownership Reconciliation
- **Defect**: Initial Batch A migration `0013_batch_a_risk_authority.py` relied on a synthetic `'default_paper_account'` fallback for unlinked decisions, lacked preflight integrity checks, and used unproven correlated alias updates that could corrupt multi-tenant ownership.
- **Remediation**:
  - Implemented 4 fail-safe preflight verification checks in `0013_batch_a_risk_authority.py`:
    1. Preflight Check 1: Detects orphan decisions (neither snapshot nor reservation evidence) and raises `RuntimeError`.
    2. Preflight Check 2: Detects conflicting evidence (snapshot points to Account A while reservation points to Account B) and raises `RuntimeError`.
    3. Preflight Check 3: Scans all legacy string aliases across `paper_account_states`, `account_snapshots`, and `risk_reservations`, verifying each matches exactly one `Account` row in the database; rejects ambiguous multi-tenant collisions with `RuntimeError`.
    4. Preflight Check 4: Verifies all existing UUID references actually exist in `accounts`.
  - Completely eliminated synthetic `'default_paper_account'` fallback.
  - Added JSON payload synchronization (`payload['account_id'] = account_id`) ensuring relational and JSON representation consistency.
  - Enforced `NOT NULL` constraint and composite index `ix_risk_decision_account_as_of`.

### 2. BATCHA-P1-002: Ambiguous Account Name Resolution Rejection
- **Defect**: Ambiguous account name resolution when multiple tenants share an account name (e.g. `'default_paper_account'`) arbitrarily selected the first matched row for ADMIN or system/userless callers.
- **Remediation**:
  - In `backend/app/services/risk/account_resolver.py`:
    - Non-admin callers: Name resolution is strictly scoped by `Account.user_id == user.id`.
    - ADMIN callers: Resolving a name that matches `>1` account across tenants raises `ValidationError` with descriptive ambiguity details.
    - System / userless callers (`user=None`): Resolving a name that matches `>1` account raises `ValidationError`.
  - In `backend/app/services/risk/account_state.py`: Removed all independent `Account.name` queries; routed all account lookups through `resolve_canonical_account`.

### 3. BATCHA-P1-003: Atomic Reservation Revocation on Terminal Transition
- **Defect**: Predecessor candidate transitions to terminal states (`INVALIDATED`, `EXPIRED`, `SUPERSEDED`) did not atomically revoke active Risk reservations, risking orphaned reservation budget blocks and concurrency races with evaluating workers.
- **Remediation**:
  - In `backend/app/services/risk/portfolio.py`: Extended `release_candidate_reservations()` to support releasing all active reservations for `candidate_id` across any accounts atomically.
  - In `backend/app/services/strategy/repository.py`: Locked predecessor candidate row under `SELECT ... FOR UPDATE` before applying terminal transitions; atomically calls `portfolio_manager.release_candidate_reservations()` in the same transaction.
  - In `backend/app/services/strategy/lifecycle.py`: Added `apply_terminal_candidate_transition()` executing candidate row-lock, transition recording, and atomic reservation revocation in a single database transaction.

### 4. BATCHA-P2-001: Operational PostgreSQL Database Migration
- **Defect**: Operational PostgreSQL database (`ai_trading` on port 5432) remained at migration `0012_phase5_reconciliation` while application expected `0013`.
- **Remediation**:
  - Completed preflight full backup of `ai_trading` using `pg_dump` into `scratch/backups/ai_trading_pre_0013.sql` (verified size 61,124,184,879 bytes).
  - Executed `alembic upgrade head` against `ai_trading`, applying `0013_batch_a_risk_authority`.
  - Verified `alembic_version` on `ai_trading` is `0013_batch_a_risk_authority (head)`.
  - Verified `account_id VARCHAR(64) NOT NULL` and index `ix_risk_decision_account_as_of` on `risk_decisions`.
  - Verified `paper_account_states.account_id` and `account_snapshots.account_id` successfully reconciled to canonical UUID `a0000000-0000-0000-0000-000000000001`.
  - Restarted `aigold-backend` service via PM2; confirmed 200 OK on `/healthz` and `/readyz` endpoints.

### 5. BATCHA-P3-001: Static Hygiene and Linter Compliance
- **Defect**: Line-length and Ruff S608 SQL query construction flags were present in Batch A modified files.
- **Remediation**:
  - Resolved all formatting and line-length issues in `backend/alembic/versions/0013_batch_a_risk_authority.py`, `backend/app/services/strategy/lifecycle.py`, and `backend/app/services/risk/repository.py`.
  - Executed `ruff check backend/` across the entire backend: 0 errors.
  - Executed `mypy` on all modified source files: 0 errors.

---

## Verification Matrix

| Suite / Gate | Test Scope | Result | Details |
|---|---|---|---|
| **Batch A Remediation Unit Suite** | AUD-P1-001 through AUD-P1-004 | **PASS** | 7 tests passed in 1.36s (`tests/test_batch_a_remediation.py`) |
| **Batch A.1 PostgreSQL Integration** | Safe migration matrix (Cases 1-8), rollback atomicity, lifecycle concurrency race, ADMIN ambiguity rejection | **PASS** | 7 tests passed in 32.10s (`tests/integration/test_batch_a1_postgres.py`) |
| **PostgreSQL 18 Integration** | Risk concurrency, multi-account, migration 0013 | **PASS** | 8 tests passed in 50.40s (`tests/integration/test_risk_postgres.py`) |
| **Foundation Gate** | Alembic upgrade/downgrade/upgrade cycle | **PASS** | 4 tests passed in 13.73s (`tests/test_foundation_gate.py`) |
| **Full Backend Unit Suite** | Complete backend test suite | **PASS** | 788 passed, 0 failed in 240s (`pytest --ignore=tests/integration -q`) |
| **Frontend Vitest Suite** | Component, contract, truthfulness tests | **PASS** | 256 passed, 0 failed in 7.88s (`npm test -- --run`) |
| **Frontend Typecheck** | TypeScript static typing | **PASS** | 0 errors (`npm run typecheck`) |
| **Frontend ESLint** | Linter rules & code hygiene | **PASS** | 0 errors (`npm run lint`) |
| **Next.js Production Build** | Production compiler & asset optimization | **PASS** | 20 routes compiled cleanly with Turbopack (`npm run build`) |
| **Operational Service Health** | PM2 runtime health & readiness | **PASS** | `/healthz` (200 OK), `/readyz` (200 OK, database: true) |

---

## Governance & Freeze Integrity
- **Freeze Baseline SHA**: `4835051b7870b293a9036a85d5c7226b1ba70af1`
- **Documentation**: [docs/FEATURE_FREEZE.md](file:///c:/AI%20Gold%20Trader/docs/FEATURE_FREEZE.md) remains unaltered and authoritative.
- **Scope Compliance**: Strictly restricted to Batch A and Batch A.1 findings. No Batch B findings touched.
