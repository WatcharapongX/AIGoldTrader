# Post-Freeze Remediation Status: Batch A (Candidate, Risk, & Account Authority)

## Executive Summary
This document records the formal remediation status for **Correction Batch A** of the post-freeze audit findings for **AIGoldTrader**. 

All four confirmed Priority 1 audit findings assigned to Batch A (AUD-P1-001 through AUD-P1-004) have been remediated, verified against PostgreSQL 18 and SQLite runtimes, and integrated into the continuous test suite. The feature freeze baseline established at `4835051b7870b293a9036a85d5c7226b1ba70af1` remains strictly governed per [FEATURE_FREEZE.md](file:///c:/AI%20Gold%20Trader/docs/FEATURE_FREEZE.md). No new trading, execution, or broker routing features were introduced.

---

## Remediated Audit Findings

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

## Database Migration: `0013_batch_a_risk_authority`

- **Revision Identifier**: `0013_batch_a_risk_authority`
- **Down Revision**: `0012_phase5_reconciliation`
- **Database Engine Compatibility**: PostgreSQL 18 (production/staging) and SQLite (in-memory/CI).
- **Operations**:
  1. Add nullable `account_id VARCHAR(64)` to `risk_decisions`.
  2. Backfill `account_id` from `account_snapshots` via `account_snapshot_id`.
  3. Backfill orphaned decisions from `risk_reservations`.
  4. Fallback default for legacy unlinked decisions (`default_paper_account`).
  5. Reconcile account name aliases across `paper_account_states`, `account_snapshots`, and `risk_decisions` to canonical account UUIDs.
  6. Enforce `NOT NULL` on `risk_decisions.account_id`.
  7. Create composite index `ix_risk_decision_account_as_of` (`account_id`, `as_of`).
  8. Enforce forward safety barrier on `downgrade()` refusing downgrade if audit rows exist.

---

## Verification Matrix

| Suite / Gate | Test Scope | Result | Details |
|---|---|---|---|
| **Batch A Remediation Unit Suite** | AUD-P1-001 through AUD-P1-004 | **PASS** | 7 tests passed in 0.97s (`tests/test_batch_a_remediation.py`) |
| **PostgreSQL 18 Integration** | Risk concurrency, multi-account, migration 0013 | **PASS** | 8 tests passed in 48.30s (`tests/integration/test_risk_postgres.py`) |
| **PostgreSQL 18 AI & Strategy** | AI safety & strategy integration | **PASS** | 2 tests passed in 23.48s (`tests/integration/test_ai_safety_postgres.py`, `tests/integration/test_strategy_postgres.py`) |
| **Foundation Gate** | Alembic upgrade/downgrade/upgrade cycle | **PASS** | 4 tests passed in 12.11s (`tests/test_foundation_gate.py`) |
| **Full Backend Unit Suite** | Complete backend test suite | **PASS** | 788 passed, 0 failed in 335.00s (`pytest --ignore=tests/integration`) |
| **Frontend Vitest Suite** | Component, contract, truthfulness tests | **PASS** | 256 passed, 0 failed in 7.54s (`npm test -- --run`) |
| **Frontend Typecheck** | TypeScript static typing | **PASS** | 0 errors (`npm run typecheck`) |
| **Frontend ESLint** | Linter rules & code hygiene | **PASS** | 0 errors (`npm run lint`) |
| **Next.js Production Build** | Production compiler & asset optimization | **PASS** | 18 routes compiled cleanly with Turbopack (`npm run build`) |

---

## Governance & Freeze Integrity
- **Freeze Baseline SHA**: `4835051b7870b293a9036a85d5c7226b1ba70af1`
- **Documentation**: [docs/FEATURE_FREEZE.md](file:///c:/AI%20Gold%20Trader/docs/FEATURE_FREEZE.md) remains unaltered and authoritative.
- **Scope Compliance**: Strictly restricted to confirmed findings AUD-P1-001, AUD-P1-002, AUD-P1-003, and AUD-P1-004.
