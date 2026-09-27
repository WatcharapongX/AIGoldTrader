# Rolling Agent Handoff — AIGoldTrader

## Session Result
- Date: 2026-09-27.
- Branch: `main`.
- Starting SHA: `03642b37f6cd093a8cf09120f90203408e97cf7c`.
- Gate: D2B1 requested-risk semantic governance clarification.
- Runtime: GPT-5.6 Sol / High.
- Result: **RESOLVED**.
- D2B1 remains **AUTHORIZED FOR IMPLEMENTATION**.
- D2B2, D2C, and D3–D7 remain **NOT AUTHORIZED**.
- No backend, frontend, test, migration, dependency, or runtime file changed.

## Resolved Four-Layer Contract
- `caller_requested_risk_pct: Decimal | None` is the exact caller input and audit evidence.
- `normalized_requested_risk_pct` preserves current live compatibility.
- Caller `None` normalizes to `policy.max_risk_per_trade_pct`.
- Caller `Decimal("0")` also normalizes to the policy maximum.
- Any other non-zero Decimal remains the normalized value.
- Zero is not newly rejected; changing that rule requires separate governance.
- `target_risk_pct` is the normalized request after deterministic pre-cap modifiers such as
  pre-news reduction and before per-trade/portfolio capacity.
- `approved_risk_pct` is the final capacity-approved value.
- Every BLOCKED pure result has approved risk equal to `Decimal("0")`.

## Amount Semantics
- `normalized_requested_risk_amount` corresponds to normalized requested risk and account equity.
- `target_risk_amount` corresponds to the post-modifier target and account equity.
- `approved_risk_amount` corresponds to final approved risk and account equity.
- All calculations preserve current Decimal behavior.
- A generic `requested_risk_amount`, if retained, means normalized requested amount.

## BLOCKED Semantic Truth
- BLOCKED `PureRiskResult` retains caller, normalized, and target values truthfully.
- Example: caller 0.50, pre-news target 0.25, later stale account block results in
  caller 0.50, normalized 0.50, target 0.25, approved 0.
- Blocking must not overwrite caller or target values with the policy maximum.

## Legacy Live Projection Boundary
- Current `_blocked_decision()` projects live `RiskDecision.requested_risk_pct` and amount
  from `policy.max_risk_per_trade_pct` regardless of caller/target values.
- This is legacy live-wrapper/public-persistence behavior, not pure semantic truth.
- D2B1 must not modify it or implement the live adapter.
- Future D2B2 must preserve that BLOCKED projection unless separate governance authorizes change.
- APPROVED/REDUCED future mapping uses normalized requested risk.

## Parity and Fingerprint Rules
- Pure/live parity compares decision, approved risk/amount, sizing, exposure, ordered reasons,
  warnings/blocks, provenance, and trigger facts.
- BLOCKED parity does not equate pure caller request with live projected requested risk.
- The additive pure fingerprint includes caller, normalized, and target risk.
- Caller `None` and explicit zero normalize equally but remain distinct audit inputs.
- Therefore `None` and zero must produce different pure semantic fingerprints.
- Existing live evaluation-intent and dependency fingerprint functions remain unchanged.

## Negative-Risk Boundary
- D2B1 must characterize `Decimal("-0.1")` against the current live oracle.
- No new negative-risk validation policy is authorized.
- Preserve current observable outcome and reason semantics where safely representable.
- If behavior is inconsistent, uncontrolled, or unsafe to represent, stop with
  **D2B1 NEGATIVE-RISK PARITY AMBIGUITY**.

## Required Requested-Risk Matrix
- Cover `None`, zero, positive below/equal/above the per-trade maximum.
- Cover normal market, pre-news reduction, early BLOCKED, capacity BLOCKED, and sizing BLOCKED.
- Assert caller, normalized, target, approved, and decision separately.
- BLOCKED cases include Kill Switch, news blackout, quote unavailable, account stale,
  daily loss, portfolio full, and sizing failure.

## Safety and Next Activity
- `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` remain unchanged.
- Broker execution remains `NONE`; AI remains advisory-only.
- Authority remains Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.
- Resume D2B1 pure-core implementation only with GPT-5.6 Sol / High.
- After implementation, run independent GPT-5.6 Sol / High verification in a fresh session.
- Do not begin D2B2, D2C, fills, PnL/metrics, persistence/API/UI, Model Routing,
  Paper Trading, OMS, broker execution, or live trading.
