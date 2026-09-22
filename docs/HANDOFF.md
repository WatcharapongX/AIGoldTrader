# Rolling Agent Handoff — AIGoldTrader

- **R0-CORR-001 baseline parent HEAD**: `095aa4827eda678467f4efa3b711f1b1fb332c72`
- **Current branch**: `main`
- **Current active batch**: `R0 — Batch B Session Security Independent Re-Verification`
- **Last completed task**: `R0-CORR-001 — Terminal Logout / Refresh Authority Remediation`

---

## 1. Corrective Change
- The confirmed defect was an expired bearer reaching `get_current_user` before the `/auth/logout` handler.
- That dependency returned 401 before Origin validation, cookie clearing, or refresh-session revocation.
- `backend/app/api/auth.py` now has a logout-specific refresh-cookie authority resolver.
- It executes only after `validate_auth_origin(request)`.
- It accepts the signed HttpOnly refresh cookie as the terminal logout authority.
- It resolves an active, unconsumed, unrevoked, unexpired server-side refresh session by hash.
- It checks that the refresh JWT subject matches that session’s server-authoritative user id.
- A refresh JWT/session mismatch revokes the affected family and clears the cookie, matching the established refresh containment behavior.
- A valid access bearer for a different subject fails closed without revoking either user’s sessions.
- Expired, missing, malformed, or non-Bearer access values are non-authoritative and do not block terminal logout.
- The existing all-active-sessions-per-user logout policy is preserved after refresh authority resolution.
- The canonical `clear_refresh_cookie()` helper remains the sole successful logout cookie-clearing mechanism.

## 2. R0 Evidence
- Exact prior path: expired bearer → `get_current_user` → 401 → logout handler not reached → refresh session survived.
- Corrected expired-bearer scenario: login 200, logout 200, response contains `Set-Cookie` with `Max-Age=0`.
- The test client no longer retained the refresh cookie after logout.
- The original server-side refresh-session row was observed with `revoked_at` set.
- Replaying the original refresh cookie immediately returned 401.
- No frontend code changed; B3/B3.3 memory-only and session-epoch controls are unaffected.

## 3. Test Results
- `backend/.venv/Scripts/python.exe -m pytest tests/test_auth.py tests/test_batch_b1_auth.py tests/test_batch_b2_cookies.py -q`: **35 passed**.
- Coverage includes valid, expired, missing, and malformed bearer logout paths.
- Coverage includes missing and invalid refresh cookies, missing and untrusted Origin, and access/refresh subject mismatch.
- Coverage includes refresh JWT/session mismatch terminal containment.
- Existing B1 atomic consumption, concurrent loser grace behavior, later replay family revocation, and rollback safety passed.
- Existing B2 cookie contract and Origin CSRF tests passed.
- `backend/.venv/Scripts/python.exe -m ruff check app/api/auth.py tests/test_auth.py`: **PASS**.

## 4. Governance Status
- **R0-P2-001**: **REMEDIATED — PENDING INDEPENDENT RE-VERIFICATION**.
- **AUD-P2-002**: **REMAINS OPEN — PENDING R0 RE-VERIFICATION**.
- **B3.2-NEW-P2-001**: **CLOSED**.
- **Batch B**: **REMAINS OPEN — PENDING R0 RE-VERIFICATION**.
- Do not mark any R0 or Batch B finding closed without an independent verification gate.

## 5. Next Authorized Task
- Run `R0 Independent Re-Verification` against the new committed main HEAD.
- Recommended model: `GPT-5.6 Sol / Medium`.
- Review `backend/app/api/auth.py`, `backend/tests/test_auth.py`, and the current batch/state documents.
- Reproduce the expired-access logout flow and independently validate post-logout refresh denial.
- Verify no regression in Batch B1 rotation, B2 cookies/Origin checks, B3 memory-only tokens, or B3.3 session epochs.
- Strictly do not start Batch C, trading execution, broker routing, OMS, or live trading.
