# Current Active Batch — AIGoldTrader

## Batch Identifier
**Batch C — External AI Runtime Safety: Scope & Architecture Planning ONLY**

## Status
**READY FOR PLANNING**

## Primary Objective
Assess and design external AI runtime safety before any provider-hardening implementation.

## Planning Scope
- Provider trust boundaries and fixture versus external-provider modes.
- Model-routing boundaries; timeout, retry, failure, fallback, budget, and concurrency behavior.
- Prompt-injection containment, structured-output validation, credential handling, data minimization, and external-data disclosure boundaries.
- AI advisory-only authority; preservation of Kill Switch and Risk Engine authority.
- Observability, test strategy, and acceptance criteria.

## Authorization Boundary
**NO IMPLEMENTATION is authorized by this batch definition.** Maintain the modular-monolith architecture.

## Strictly Out of Scope
- Changing provider code or model configuration.
- Live trading, broker execution, OMS, paper execution, or Backtesting Engine implementation.
- Hermes integration, MCP integration, or TradingView integration.
- New infrastructure, Redis, Kafka, Celery, Kubernetes, microservices, Vector DB, ML pipelines.
