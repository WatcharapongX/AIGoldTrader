# Rolling Agent Handoff — AIGoldTrader

- **R0-CORR-002B baseline parent HEAD**: `7e9c530cf5ba8491450ef2dc49efe7772fea1247`
- **Current branch**: `main`
- **Current active batch**: `R0 — Batch B Session Security Independent Re-Verification`
- **Latest implementation work**: `R0-CORR-002C — Deterministic PostgreSQL Serialization Evidence`

---

## 1. Corrective Change

- Refresh and logout now serialize refresh-authority mutations with one transaction-scoped PostgreSQL advisory lock per `user_id`.
- The key is the signed big-endian first 64 bits of `SHA-256(b"aigold:auth-user:v1:" + user_id.bytes)`; it is deterministic across workers and restarts.
- Both paths resolve only immutable session routing fields before acquiring the lock, then scalar-project authoritative mutable state after the lock.
- Refresh arrival is captured with PostgreSQL `clock_timestamp()` before waiting; loser classification compares it to the actual PostgreSQL consume timestamp.
- PostgreSQL consumption writes `clock_timestamp()` (not transaction-start `now()`); SQLite retains its compatible timestamp only in the unit harness.
- Logout accepts an active presented session or a session consumed by a concurrently started refresh within the existing five-second grace window.
- Logout then set-revokes every active refresh session for the user in one database UPDATE.
- A PostgreSQL-local five-second `lock_timeout` bounds acquisition; failure aborts and cannot mutate without serialized authority.
- Success cookies are emitted only after commit. Concurrent refresh losers stay 401 without cookie deletion; terminal paths retain clear-cookie behavior.

## 2. Root-Cause Protection

- The stale logout snapshot race is closed: logout rereads post-lock state and revokes the current user-wide active authority set.
- The identity-map/lock-wait regression is closed: every post-wait decision uses a fresh scalar projection, never a pre-lock ORM entity.
- Refresh-first logout observes and revokes the successor; logout-first prevents a waiting refresh from leaving authority behind.

## 3. Targeted PostgreSQL Evidence

- `test_refresh_logout_serialization_prerequisites`: PostgreSQL isolation is `read committed`; advisory-key stability verified.
- `test_atomic_refresh_http_concurrency_100_iterations`: 100 iterations; one 200 and one 401; loser has no `Max-Age=0`; one successor is active before logout.
- `test_postgres_logout_first_serializes_refresh_authority`: post-lock gate; logout 200, waiting refresh 401, active authority count 0.
- `test_postgres_refresh_first_logout_revokes_successor`: post-lock gate; refresh 200, logout 200, active authority count 0, successor refresh 401.
- `test_postgres_replay_grace_family_revocation_and_rollback`: immediate loser preserves cookie, late replay clears/revokes family, injected audit failure rolls back and retry succeeds.
- `test_postgres_true_concurrent_refresh_logout_is_terminal`: both requests reach the production lock helper before release; successful logout leaves no authority.
- `test_postgres_lock_wait_beyond_grace_preserves_concurrent_loser`: a real PostgreSQL advisory-lock wait over five seconds remains a 401 without cookie deletion.
- `test_postgres_cross_user_authority_locks_are_isolated`: User B rotates while User A is lock-held; keys and persisted authority remain isolated.
- `test_postgres_post_lock_scalar_reread_defeats_stale_identity_map`: a deliberately stale ORM row remains stale while the production scalar reread sees consumption.
- `test_postgres_browser_response_ordering_cannot_restore_authority`: applying a stale successor cookie after logout remains server-side 401.
- `test_postgres_authority_lock_timeout_fails_closed`: real five-second timeout yields no consumption, successor, or refresh audit; retry succeeds once released.

## 4. Test Results

- `backend/.venv/Scripts/python.exe -m pytest tests/integration/test_batch_b1_postgres.py -q`: **12 passed**.
- `backend/.venv/Scripts/python.exe -m pytest tests/test_auth.py tests/test_batch_b1_auth.py tests/test_batch_b2_cookies.py -q`: **35 passed**.
- `backend/.venv/Scripts/python.exe -m ruff check app/api/auth.py app/services/refresh_sessions.py tests/integration/test_batch_b1_postgres.py`: **PASS**.

## 5. Governance Status

- **R0-P2-001**: **REMEDIATED — PENDING INDEPENDENT RE-VERIFICATION**.
- **AUD-P2-002**: **REMAINS OPEN — PENDING R0 RE-VERIFICATION**.
- **B3.2-NEW-P2-001**: **CLOSED**.
- **Batch B**: **REMAINS OPEN — PENDING R0 RE-VERIFICATION**.
- Do not mark any R0 or Batch B finding closed without the independent gate.

## 6. Next Authorized Task

- Run `R0 Independent Re-Verification` against the committed main HEAD.
- Recommended model: `GPT-5.6 Sol / Medium`.
- Independently reproduce refresh/logout ordering under real PostgreSQL.
- Strictly do not start Batch C, trading execution, broker routing, OMS, or live trading.
