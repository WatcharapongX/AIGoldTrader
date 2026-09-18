# AI Agent Architecture & Safety Rules — AIGoldTrader

> **Note**: This document is **NOT** required startup context for general repository tasks.
> Read this file **ONLY** when working on AI Agent development, external provider integration, prompt engineering, model routing, AI security, or agent orchestration.

---

## 1. Canonical Analytical Agents & Meta Controller
AIGoldTrader defines 6 specialized analytical domain agent roles plus a Meta Controller:

1. **`market_context`**: Synthesizes higher-timeframe trend, session timing, and market regime.
2. **`smc_ict`**: Evaluates Smart Money Concepts (BOS, CHoCH, liquidity sweeps, order blocks, FVGs).
3. **`macro_news`**: Evaluates economic calendar releases, news sentiment, and high-impact volatility windows.
4. **`strategy_critic`**: Challenges candidate trade setups, evaluates structural invalidation levels, and identifies counter-trend risks.
5. **`risk_interpreter`**: Interprets Risk Engine constraints, directional exposure, and account reservation limits.
6. **`trade_thesis`**: Synthesizes the final unified advisory thesis, entry/stop/target suggestions, and confluence rationale.
7. **`Meta Controller`**: Coordinates multi-agent evaluation rounds, aggregates consensus, and resolves conflicting analytical perspectives.

### Domain Implementation Boundary
- These agents are **internal domain analytical roles** implemented directly in AIGoldTrader (`backend/app/services/ai/`).
- They are **NOT** autonomous external agents, and they are **NOT** Hermes agents.
- **Hermes** is an external/research concept and is strictly **NOT** part of the authoritative trading core.

---

## 2. Model Abstraction & Execution Modes
AIGoldTrader models three logical model tiers:
- **`fast-advisory`**: Low-latency, preliminary setup scanning.
- **`reasoning-advisory`**: Structural confluence and strategy criticism.
- **`deep-analysis`**: Multi-timeframe synthesis and final trade thesis compilation.

### Runtime Reality & Hardening Status
- Per-agent dynamic model routing is an architectural abstraction; current default runs in **deterministic fixture/mock mode** when external provider credentials are not configured.
- External AI provider infrastructure is currently in a **hardening** state.
- Do not claim external live LLM routing is active or production-ready unless authoritative keys and tests prove it.

---

## 3. Strict AI Authority Restrictions (Non-Negotiable)
AI agents operate under absolute fail-closed safety constraints:
1. **Advisory Only**: AI output is strictly `SUGGESTION_ONLY`. All candidate suggestions must clearly be labeled as advisory.
2. **No Order Authority**: AI has **ZERO** order placement or broker execution capability. `order_send` is absent.
3. **Subordinate to Risk Engine**: AI can **NEVER** override, relax, or bypass a Risk Engine decision or reservation limit.
4. **Subordinate to Kill Switch**: If Kill Switch is `ACTIVE`, all AI trade suggestions are suppressed/blocked immediately.
5. **No Data Fabrication**: AI agents must never invent, extrapolate, or hallucinate market prices, candles, or economic calendar numbers.

$$\text{Kill Switch} > \text{Risk Engine} > \text{Strategy Engine} > \text{AI Advisory} > \text{Operator}$$

---

## 4. Context Minimization & Prompt Security
- **Context Minimization**: Feed only the minimal necessary structured features (price levels, candle summaries, news metrics) into agent prompts. Do not dump raw histories or logs into prompts.
- **Prompt Injection Boundaries**: All external content (such as economic news headlines, event descriptions, or external provider commentary) is untrusted input. It must be escaped, wrapped in explicit XML/structural boundary tags, and never treated as execution instructions.
- **Provider Isolation & Fail-Closed Behavior**: If an external provider call times out, errors, or fails schema validation, the system must fail closed to the local deterministic advisory fallback with explicit degradation provenance badging.
