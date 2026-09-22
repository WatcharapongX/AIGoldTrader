# Current Active Batch — AIGoldTrader

## Batch Identifier
**R0 — Batch B Session Security Independent Re-Verification**

## Status
**READY FOR INDEPENDENT RE-VERIFICATION**

## Primary Objective
Conduct independent security verification (GPT-5.6 Sol / Medium) of the Batch B browser authentication and session management remediation, covering:
- **R0-P2-001**: Explicit logout is terminal for the server-side refresh authority with valid, expired, missing, or malformed access bearers.
- **AUD-P2-002**: Memory-only access token, HttpOnly refresh cookie, multi-tab Web Locks/BroadcastChannel coordination, canonical invalidation.
- **B3.2-NEW-P2-001**: Request sessionEpoch binding on 401 recovery, terminal recovery barrier, and elimination of post-logout token resurrection.

## In Scope (Verification Only)
1. Verification of Batch B3 series commits:
   - `ea01150`: Memory-only access token & auth coordinator.
   - `6507b87`: Batch B3.1 coordinator race and terminal invalidation closure.
   - `24d7e7c`: Batch B3.2 global application entry storage cutover.
   - `5e6d794`: Batch B3.3 request sessionEpoch binding & late-401 resurrection closure.
   - R0-CORR-001 corrective commit: logout-specific refresh-cookie authority and terminal server-side revocation.
2. Verification of test suites:
   - `frontend/tests/b3-auth-coordinator.test.cjs` (17/17 pass)
   - `frontend/tests/b3-2-storage-cutover.test.cjs` (7/7 pass)
   - `frontend/tests/b3-3-epoch-recovery.test.cjs` (10/10 pass)
   - Full frontend suite: `npm test` (290/290 pass)
   - Backend auth regression: `pytest` (28/28 pass)
3. Verification of static storage invariants:
   - Zero `localStorage` or `sessionStorage` access_token writes/reads.
   - Zero token query strings in WebSocket or HTTP URLs.
   - Zero raw tokens in BroadcastChannel payloads.

## Strictly Out of Scope
- **DO NOT START BATCH C**.
- No external AI architecture changes or provider expansions.
- No Backtesting Engine implementation.
- No Paper Trading execution engine.
- No Order Management System (OMS) implementation.
- No Model Context Protocol (MCP) or Hermes agent integration.
- No TradingView integration.
- No Broker execution or MT5 order routing.
- No Live trading.

## Rule for Future Agents
When this batch completes verification and is closed by the user/verifier, replace the contents of this file with the new authorized batch definition. Do not accumulate historical batch logs in this file.
