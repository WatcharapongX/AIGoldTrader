# Post-Freeze Remediation Status: Batch A, Batch A.1, Batch A.2 & Batch A.3

## Executive Summary
This document records the formal remediation status for **Correction Batch A**, **Correction Batch A.1**, **Correction Batch A.2** (Canonical Account Authority Hardening), and **Correction Batch A.3** (Referential Integrity Closure) of the post-freeze audit findings for **AIGoldTrader**.

All confirmed audit findings assigned to Batch A (AUD-P1-001 through AUD-P1-004), corrective findings assigned to Batch A.1 (BATCHA-P1-001 through BATCHA-P1-003, BATCHA-P2-001, BATCHA-P3-001), hardening findings assigned to Batch A.2 (BATCHA1-NEW-P1-001, BATCHA1-NEW-P2-001, BATCHA1-NEW-P2-002, BATCHA1-NEW-P3-001), and final referential integrity findings assigned to Batch A.3 (BATCHA2-NEW-P1-001, BATCHA2-NEW-P2-001, BATCHA2-NEW-P2-002) have been remediated, verified against PostgreSQL 18.6 and SQLite runtimes, and integrated into the continuous test suite. The feature freeze baseline established at `4835051b7870b293a9036a85d5c7226b1ba70af1` remains strictly governed per [FEATURE_FREEZE.md](file:///c:/AI%20Gold%20Trader/docs/FEATURE_FREEZE.md). No new trading, execution, or broker routing features were introduced.

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

## Remediated Audit Findings: Batch A.2 (Canonical Account Authority Hardening)

### 1. BATCHA1-NEW-P1-001: Canonical Account Authority Post-Resolution Hardening
- **Defect**: Downstream components (`account_state.py`, `repository.py`, and `assembler.py`) exhibited query fallbacks to raw unparsed input names or `acc_row.name` rather than strictly utilizing the resolved canonical UUID.
- **Remediation**:
  - In `backend/app/services/risk/account_state.py`: All state queries strictly use canonical UUID `canonical_id = str(acc_row.id)`. Removed legacy fallback lookups.
  - In `backend/app/services/risk/repository.py`: `get_authoritative_account_snapshot()` and `persist_risk_decision()` strictly bind to canonical account UUID.
  - In `backend/app/services/ai/assembler.py`: Query filters on `AccountRecord.id == canonical_account_id` without joining or falling back to raw name strings.

### 2. BATCHA1-NEW-P2-001: Pre-Upgrade 0012 Account Reconciliation Normalizer
- **Defect**: Databases at migration `0012` where an alias snapshot and a UUID reservation referenced the same physical account could trigger false-positive conflict aborts during upgrade without an external normalizer.
- **Remediation**:
  - Created standalone idempotent pre-upgrade script `backend/app/scripts/normalize_0012_accounts.py`.
  - Normalizer supports both SQLAlchemy `Connection` and raw DBAPI / `psycopg` connections via `DBAdapter`.
  - Resolves snapshot alias and reservation UUID for the same account to the canonical `Account.id` before migration.
  - Safely aborts with rollback on true cross-account conflicts or duplicate aliases across tenants.
  - Preserved deployed migration `0013_batch_a_risk_authority.py` completely immutable.

### 3. BATCHA1-NEW-P2-002: Strict UUID & Foreign Key Invariants on Risk Decisions
- **Defect**: `RiskDecision.account_id` lacked strict UUID validation at the service boundary and relational database foreign-key enforcement to `accounts(id)`.
- **Remediation**:
  - In `backend/app/services/risk/domain.py`: `RiskDecision.account_id` is mandatory non-nullable string without default.
  - In `backend/app/models/risk.py`: Removed default paper account from `RiskDecisionRecord.account_id`.
  - In `backend/app/services/risk/repository.py`: `persist_risk_decision()` strictly parses `uuid.UUID(str(decision.account_id))` and verifies existence against authoritative `accounts` store; synchronizes relational `account_id` with `payload["account_id"]`.
  - Created migration `0014_batch_a2_account_authority.py` adding:
    1. Check constraint `ck_risk_decision_account_id_strict_uuid` enforcing regex format `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`.
    2. PostgreSQL trigger `trg_risk_decision_account_fk` (`AFTER INSERT OR UPDATE`) executing function `check_risk_decision_account_exists()` to enforce referential integrity to `accounts(id)`.
  - Applied migration `0014` to operational database `ai_trading` after full pre-migration `pg_dump` backup.

### 4. BATCHA1-NEW-P3-001: Type Annotation Completeness
- **Defect**: Missing explicit type annotation on `values_dict` in `account_state.py`.
- **Remediation**:
  - Added explicit annotation `values_dict: dict[str, Any]` in `PaperAccountStateService.refresh_paper_account_snapshot()`.

---

## Remediated Audit Findings: Batch A.3 (Referential Integrity Closure)

### 1. BATCHA2-NEW-P1-001: Native UUID & Real Foreign Key Referential Integrity
- **Defect**: `risk_decisions.account_id` was stored as `VARCHAR(64)` and referential integrity relied on a temporary 0014 trigger (`trg_risk_decision_account_fk`) and regex check constraint (`ck_risk_decision_account_id_strict_uuid`), which was not delete-safe (did not prevent orphaned decisions upon account deletion).
- **Remediation**:
  - In `backend/app/models/risk.py`: Converted `risk_decisions.account_id` from `VARCHAR(64)` to native `Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)`.
  - Added `@validates("account_id")` on `RiskDecisionRecord` to coerce input string UUIDs seamlessly into `uuid.UUID`.
  - In `backend/app/db/base.py`: Enhanced generic `Uuid` mapping with `GUID(TypeDecorator[uuid.UUID])` ensuring transparent string coercion on SQLite test environments while compiling to native PostgreSQL `UUID`.
  - Created migration `0015_batch_a3_risk_account_fk.py`:
    1. Preflight validation verifying UUID syntax, existence in `accounts(id)`, and payload equality.
    2. Drops 0014 workaround trigger `trg_risk_decision_account_fk` and function `check_risk_decision_account_exists()`.
    3. Drops 0014 check constraint `ck_risk_decision_account_id_strict_uuid`.
    4. Alters `account_id` type to native `UUID USING account_id::uuid`.
    5. Adds real Foreign Key `fk_risk_decisions_account_id_accounts` referencing `accounts(id)` with `ON DELETE RESTRICT`.
  - Tested on real PostgreSQL: deleting an account referenced by a `RiskDecision` is rejected by the database with `RestrictViolation` / `ForeignKeyViolation`. Both Account and Decision records are preserved.

### 2. BATCHA2-NEW-P2-001: Continuous Database-Level Payload Equality & Authoritative Hydration
- **Defect**: `RiskDecision.account_id` in the serialized JSON payload could desynchronize from the relational column. `GET /risk/decisions/{id}` validated raw `row.payload` rather than authoritatively hydrating from relational columns.
- **Remediation**:
  - In `backend/alembic/versions/0015_batch_a3_risk_account_fk.py`: Added PostgreSQL database check constraint `ck_risk_decision_payload_account_id` checking `(payload ? 'account_id') AND ((payload ->> 'account_id')::uuid = account_id)`. Direct DB inserts/updates with mismatched, missing, or altered payload account IDs are rejected with `CheckViolation`.
  - In `backend/app/services/risk/repository.py`:
    - Created single authoritative `hydrate_risk_decision(record: RiskDecisionRecord) -> RiskDecision` enforcing that `record.account_id` always supersedes any serialized payload value.
    - Updated `find_existing_decision()`, `persist_risk_decision()`, and `list_recent_decisions()` to use `hydrate_risk_decision()`.
    - `persist_risk_decision()` wraps unique constraint collision checks in `session.begin_nested()` (savepoint) to prevent outer transaction abort on PostgreSQL.
  - In `backend/app/api/risk.py`: Replaced raw `RiskDecision.model_validate(row.payload)` in `get_decision_by_id()` with `hydrate_risk_decision(row)`.
  - In `backend/app/services/ai/assembler.py`: Scoped decision queries using UUID-safe comparison `RiskDecisionRecord.account_id == acc_row.id`.

### 3. BATCHA2-NEW-P2-002: Exact Revision Guard for 0012 Normalizer & Canonical Safe DB Upgrade Entrypoint
- **Defect**: The 0012 normalizer lacked exact revision guards for future revisions (0013, 0014, 0015) and there was no transactional CLI wrapper orchestrating normalization before Alembic migrations.
- **Remediation**:
  - In `backend/app/scripts/normalize_0012_accounts.py`: Implemented exact revision guard: strictly allows revision `0012`, skips `0013/0014/0015`, and aborts on `0011`, base, missing, or unexpected revisions.
  - Created standalone CLI tool `backend/app/scripts/safe_db_upgrade.py` (`python -m app.scripts.safe_db_upgrade`):
    - Inspects current revision; if 0012, runs `normalize_0012_database` inside a dedicated transaction; aborts and rolls back on error before Alembic is touched.
    - Executes Alembic upgrade to head (`0015_batch_a3_risk_account_fk`).
    - Masks credentials in all log outputs.
  - Updated documentation (`README.md`, `docs/18-devops.md`) to establish `safe_db_upgrade` as the canonical migration command.

---

## Verification Matrix

| Suite / Gate | Test Scope | Result | Details |
|---|---|---|---|
| **Batch A Remediation Unit Suite** | AUD-P1-001 through AUD-P1-004 | **PASS** | 7 tests passed (`tests/test_batch_a_remediation.py`) |
| **Batch A.3 PostgreSQL Integration** | Safe migration normalizer, 0015 invariants, real FK restrict, payload check constraint, hydration, lifecycle races, RBAC & tenant isolation | **PASS** | 14 tests passed in 53.0s (`tests/integration/test_batch_a1_postgres.py`) |
| **PostgreSQL 18 Concurrency Integration** | Risk concurrency, multi-account, migration 0015 | **PASS** | 8 tests passed in 63.5s (`tests/integration/test_risk_postgres.py`) |
| **Foundation Gate** | Alembic upgrade/downgrade/upgrade cycle (up to 0015) | **PASS** | 12 tests passed in 97.3s (`tests/integration/test_postgres.py`) |
| **Full Backend Unit Suite** | Complete backend test suite | **PASS** | 788 passed, 0 failed in 294s (`pytest --ignore=tests/integration -q`) |
| **Frontend Vitest Suite** | Component, contract, truthfulness tests | **PASS** | 256 passed, 0 failed in 9.5s (`npm test -- --run`) |
| **Frontend Typecheck** | TypeScript static typing | **PASS** | 0 errors (`npm run typecheck`) |
| **Frontend ESLint** | Linter rules & code hygiene | **PASS** | 0 errors (`npm run lint`) |
| **Next.js Production Build** | Production compiler & asset optimization | **PASS** | 20 routes compiled cleanly with Turbopack (`npm run build`) |
| **Operational Service Health** | PM2 runtime health & readiness | **PASS** | `/healthz` (200 OK), `/readyz` (200 OK, database: true) |

---

## Governance & Freeze Integrity
- **Freeze Baseline SHA**: `4835051b7870b293a9036a85d5c7226b1ba70af1`
- **Documentation**: [docs/FEATURE_FREEZE.md](file:///c:/AI%20Gold%20Trader/docs/FEATURE_FREEZE.md) remains unaltered and authoritative.
- **Scope Compliance**: Strictly restricted to Batch A, Batch A.1, Batch A.2, and Batch A.3 findings. No Batch B findings touched.
