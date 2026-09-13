"""Exactly six analytical agents + Meta Controller implementation.

All agents perform context minimization, strict output validation,
and adhere strictly to advisory-only boundaries.
"""

import datetime as dt
import logging
from typing import Any

from app.services.ai.domain import (
    META_CONTROLLER_ID,
    AgentAgreement,
    AgentAnalysisResult,
    AIAnalysisInput,
    AIAnalysisResult,
    DirectionalBias,
    MetaStatus,
    fingerprint,
)
from app.services.ai.prompts import get_prompt, wrap_untrusted_data
from app.services.ai.provider import AIProvider, ModelConfig

logger = logging.getLogger(__name__)


def compute_agent_agreement(biases: list[DirectionalBias]) -> AgentAgreement:
    """Deterministically compute agreement level across analytical agents."""
    valid_biases = [b for b in biases if b in ("LONG", "SHORT")]
    if not valid_biases:
        return "LOW"

    long_count = valid_biases.count("LONG")
    short_count = valid_biases.count("SHORT")
    total = len(valid_biases)

    if long_count == total or short_count == total:
        return "HIGH"
    if min(long_count, short_count) >= 2:
        return "CONFLICTING"
    if min(long_count, short_count) == 1 and total >= 4:
        return "MEDIUM"
    return "LOW"


class BaseAnalyticalAgent:
    """Base class for the six specialized analytical agents."""

    agent_id: str
    prompt_id: str

    def __init__(self, agent_id: str, prompt_id: str):
        self.agent_id = agent_id
        self.prompt_id = prompt_id

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        """Context minimization hook. Subclasses override to extract only relevant context."""
        return {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
        }

    async def execute(
        self,
        ai_input: AIAnalysisInput,
        provider: AIProvider,
        config: ModelConfig,
        timeout_seconds: float | None = None,
    ) -> AgentAnalysisResult:
        """Execute agent analysis with strict error isolation and schema validation."""
        now_utc = dt.datetime.now(dt.UTC)
        context = self.extract_context(ai_input)
        wrapped_payload = wrap_untrusted_data(context)
        system_prompt = get_prompt(self.prompt_id)

        try:
            res = await provider.analyze(
                agent_id=self.agent_id,
                system_prompt=system_prompt,
                user_payload=wrapped_payload,
                model_config=config,
                timeout_seconds=timeout_seconds,
            )
            raw = dict(res.raw_payload)

            # Enforce server-side authoritative fields that cannot be forged by model
            raw["agent_id"] = self.agent_id
            raw["agent_version"] = "ai-1.0.0"
            raw["provider_provenance"] = config.provider
            raw["prompt_version"] = self.prompt_id
            raw["generated_at"] = now_utc.isoformat()
            raw["as_of"] = ai_input.as_of.isoformat()
            raw["token_usage"] = {
                "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
                "total_tokens": res.total_tokens,
            }

            return AgentAnalysisResult.model_validate(raw)

        except Exception as exc:
            logger.warning("Agent %s execution failed: %s", self.agent_id, exc)
            return AgentAnalysisResult(
                agent_id=self.agent_id,
                agent_version="ai-1.0.0",
                status="DEGRADED",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                summary_th=f"การวิเคราะห์ของ {self.agent_id} ไม่พร้อมใช้งาน: {exc}",
                evidence_refs=(),
                supporting_factors_th=(),
                conflicting_factors_th=(),
                warnings_th=(str(exc),),
                missing_context_th=(f"Agent failure: {exc}",),
                provider_provenance=config.provider,
                prompt_version=self.prompt_id,
                generated_at=now_utc,
                as_of=ai_input.as_of,
                token_usage=None,
            )


class MarketContextAgent(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("market_context", "market_context.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "quote": ai_input.market_quote,
            "regime": ai_input.market_structure_context.get("regime", "UNKNOWN"),
            "sessions": ai_input.market_structure_context.get("current_sessions", []),
            "indicators": ai_input.market_structure_context.get("indicators", {}),
        }


class SMCICTAnalyst(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("smc_ict", "smc_ict.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "internal_state": ai_input.market_structure_context.get("internal_state", "UNKNOWN"),
            "external_state": ai_input.market_structure_context.get("external_state", "UNKNOWN"),
            "swings_count": len(ai_input.market_structure_context.get("swings", [])),  # type: ignore[arg-type]
            "events": ai_input.market_structure_context.get("events", [])[:10],
            "liquidity": ai_input.market_structure_context.get("liquidity", [])[:10],
            "zones": ai_input.market_structure_context.get("zones", [])[:10],
            "dealing_range": ai_input.market_structure_context.get("dealing_range"),
        }


class MacroNewsAnalyst(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("macro_news", "macro_news.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "news_context": ai_input.news_context,
            "news_provenance": ai_input.news_provenance,
        }


class StrategyCritic(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("strategy_critic", "strategy_critic.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "candidate": ai_input.strategy_candidate,
            "plan_summary": {
                "direction": ai_input.trade_plan.get("direction"),
                "score": ai_input.trade_plan.get("score"),
                "invalidation_th": ai_input.trade_plan.get("invalidation_th"),
                "warnings_th": ai_input.trade_plan.get("warnings_th", []),
            },
        }


class RiskInterpreter(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("risk_interpreter", "risk_interpreter.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "risk_decision": ai_input.risk_decision,
            "kill_switch_state": ai_input.kill_switch_state,
        }


class TradeThesisAgent(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("trade_thesis", "trade_thesis.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "strategy_direction": ai_input.strategy_candidate.get("direction"),
            "strategy_score": ai_input.strategy_candidate.get("score"),
            "risk_status": ai_input.risk_decision.get("decision"),
            "kill_switch_state": ai_input.kill_switch_state.get("state"),
        }


def get_all_analytical_agents() -> tuple[BaseAnalyticalAgent, ...]:
    """Factory returning exactly six analytical agents in stable canonical order."""
    return (
        MarketContextAgent(),
        SMCICTAnalyst(),
        MacroNewsAnalyst(),
        StrategyCritic(),
        RiskInterpreter(),
        TradeThesisAgent(),
    )


class MetaController:
    """Synthesizes the six analytical agent results into an executive advisory report."""

    def __init__(self):
        self.agent_id = META_CONTROLLER_ID
        self.prompt_id = "meta_controller.v1"

    async def execute(
        self,
        ai_input: AIAnalysisInput,
        agent_results: dict[str, AgentAnalysisResult],
        provider: AIProvider,
        config: ModelConfig,
        timeout_seconds: float | None = None,
    ) -> AIAnalysisResult:
        now_utc = dt.datetime.now(dt.UTC)

        # 1. Compute deterministic agreement and check agent statuses
        biases = [res.directional_bias for res in agent_results.values() if res.status == "READY"]
        agreement = compute_agent_agreement(biases)

        # 2. Prepare meta synthesis payload
        meta_context = {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "risk_decision": ai_input.risk_decision.get("decision"),
            "kill_switch_state": ai_input.kill_switch_state.get("state"),
            "agent_agreement": agreement,
            "agent_summaries": {
                aid: {
                    "bias": res.directional_bias,
                    "strength": res.evidence_strength,
                    "status": res.status,
                    "summary_th": res.summary_th,
                    "warnings_th": list(res.warnings_th),
                }
                for aid, res in agent_results.items()
            },
        }

        wrapped_payload = wrap_untrusted_data(meta_context)
        system_prompt = get_prompt(self.prompt_id)

        try:
            res = await provider.analyze(
                agent_id=self.agent_id,
                system_prompt=system_prompt,
                user_payload=wrapped_payload,
                model_config=config,
                timeout_seconds=timeout_seconds,
            )
            raw = dict(res.raw_payload)

            bias = raw.get("directional_bias", "NEUTRAL")
            if bias not in ("LONG", "SHORT", "NEUTRAL", "NO_BIAS"):
                bias = "NEUTRAL"
            strength = raw.get("evidence_strength", "MODERATE")
            if strength not in ("STRONG", "MODERATE", "WEAK", "INSUFFICIENT"):
                strength = "MODERATE"

            summary_th = str(raw.get("summary_th", "สรุปผลการวิเคราะห์ภาพรวมโดย AI"))
            key_evidence_th = tuple(str(x) for x in raw.get("key_evidence_th", []))
            conflicts_th = tuple(str(x) for x in raw.get("conflicts_th", []))
            risk_notes_th = tuple(str(x) for x in raw.get("risk_notes_th", []))
            warnings_th = tuple(str(x) for x in raw.get("warnings_th", []))

        except Exception as exc:
            logger.warning("MetaController synthesis failed: %s", exc)
            bias = "NEUTRAL"
            strength = "INSUFFICIENT"
            summary_th = f"การประมวลผล Meta Controller เกิดข้อผิดพลาด: {exc}"
            key_evidence_th = ()
            conflicts_th = ()
            risk_notes_th = ("Meta Controller failed",)
            warnings_th = (str(exc),)

        # 3. Derive meta status based on agent results
        ready_count = sum(1 for r in agent_results.values() if r.status == "READY")
        if ready_count == 6:
            meta_status: MetaStatus = "READY"
        elif ready_count >= 4:
            meta_status = "PARTIAL"
        elif ready_count >= 1:
            meta_status = "DEGRADED"
        else:
            meta_status = "UNAVAILABLE"

        prompt_versions = {res.agent_id: res.prompt_version for res in agent_results.values()}
        prompt_versions[self.agent_id] = self.prompt_id

        # Compute semantic fingerprints
        semantic_data = {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "status": meta_status,
            "directional_bias": bias,
            "evidence_strength": strength,
            "agent_agreement": agreement,
            "agent_biases": {k: v.directional_bias for k, v in sorted(agent_results.items())},
            "risk_decision_id": str(ai_input.risk_decision.get("id", "")),
        }
        analysis_fp = fingerprint(semantic_data)

        return AIAnalysisResult(
            analysis_id=f"ai_{analysis_fp[:32]}",
            symbol=ai_input.symbol,
            as_of=ai_input.as_of,
            status=meta_status,
            directional_bias=bias,  # type: ignore[arg-type]
            evidence_strength=strength,  # type: ignore[arg-type]
            agent_agreement=agreement,
            summary_th=summary_th,
            key_evidence_th=key_evidence_th,
            conflicts_th=conflicts_th,
            risk_notes_th=risk_notes_th,
            warnings_th=warnings_th,
            agent_results=agent_results,
            strategy_id=str(ai_input.strategy_candidate.get("strategy_id", "")),
            strategy_version=str(ai_input.strategy_candidate.get("strategy_version", "")),
            risk_decision_id=str(ai_input.risk_decision.get("id", "")),
            risk_decision_status=str(ai_input.risk_decision.get("decision", "")),
            kill_switch_state=str(ai_input.kill_switch_state.get("state", "INACTIVE")),
            provider_provenance=config.provider,
            prompt_versions=prompt_versions,
            generated_at=now_utc,
            input_fingerprint=ai_input.input_fingerprint,
            analysis_fingerprint=analysis_fp,
            execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
        )
