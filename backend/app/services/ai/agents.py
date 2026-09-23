"""Exactly six analytical agents + Meta Controller implementation.

All agents perform context minimization, strict output validation,
and adhere strictly to advisory-only boundaries.
"""

import datetime as dt
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services.ai.domain import (
    META_CONTROLLER_ID,
    AgentAgreement,
    AgentAnalysisResult,
    AIAnalysisInput,
    AIAnalysisResult,
    AIProviderExecutionProvenance,
    DirectionalBias,
    EvidenceStrength,
    MetaStatus,
    fingerprint,
)
from app.services.ai.prompts import build_structured_payload, get_prompt
from app.services.ai.provider import (
    ModelConfig,
    ProviderDescriptor,
    ProviderRequestError,
    analyze_with_controls,
    public_provider_failure_code,
)

logger = logging.getLogger(__name__)


def _execution_provenance(res: Any, config: ModelConfig) -> AIProviderExecutionProvenance:
    """Build server-authoritative provenance from a completed provider result."""
    provider_type = res.provider_type
    return AIProviderExecutionProvenance(
        provider_id=res.provider_id,
        provider_type=provider_type,
        model_alias=config.model_alias,
        model_used=res.model_used,
        mode="fixture" if provider_type == "fixture" else "external",
    )


def compute_agent_agreement(biases: list[DirectionalBias]) -> AgentAgreement:
    """Deterministically compute agreement level across analytical agents."""
    if not biases:
        return "UNAVAILABLE"
    if all(b == "NO_BIAS" for b in biases):
        return "UNAVAILABLE"
    valid_biases = [b for b in biases if b in ("LONG", "SHORT")]
    if not valid_biases:
        return "LOW" if any(b == "NEUTRAL" for b in biases) else "UNAVAILABLE"

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

    def extract_untrusted_evidence(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        """Return role evidence that must remain outside the trusted instruction context."""
        return {}

    async def execute(
        self,
        ai_input: AIAnalysisInput,
        provider: ProviderDescriptor,
        config: ModelConfig,
        timeout_seconds: float | None = None,
    ) -> AgentAnalysisResult:
        """Execute agent analysis with strict error isolation and schema validation."""
        if not isinstance(provider, ProviderDescriptor):
            raise ProviderRequestError(
                f"BaseAnalyticalAgent.execute requires ProviderDescriptor; "
                f"live {type(provider).__name__} instances are prohibited"
            )
        now_utc = dt.datetime.now(dt.UTC)
        trusted_context = {
            "agent_id": self.agent_id,
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            **self.extract_context(ai_input),
        }
        system_prompt = get_prompt(self.prompt_id)
        structured_payload = build_structured_payload(
            trusted_context,
            self.extract_untrusted_evidence(ai_input),
        )
        actual_prov = provider.provider_id
        execution_provenance: AIProviderExecutionProvenance | None = None

        try:
            res = await analyze_with_controls(
                provider,
                agent_id=self.agent_id,
                system_prompt=system_prompt,
                user_payload=structured_payload,
                model_config=config,
                timeout_seconds=timeout_seconds,
            )
            raw = dict(res.raw_payload)
            execution_provenance = _execution_provenance(res, config)

            # Enforce server-side authoritative fields that cannot be forged by model
            raw["agent_id"] = self.agent_id
            raw["agent_version"] = "ai-1.0.0"
            raw["provider_provenance"] = execution_provenance.provider_id
            raw["execution_provenance"] = execution_provenance.model_dump(mode="json")
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
            failure_code = public_provider_failure_code(exc)
            logger.warning(
                "Agent execution failed: agent_id=%s provider_id=%s failure_code=%s exception_class=%s",
                self.agent_id,
                actual_prov,
                failure_code,
                type(exc).__name__,
            )
            return AgentAnalysisResult(
                agent_id=self.agent_id,
                agent_version="ai-1.0.0",
                status="DEGRADED",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                summary_th=f"การวิเคราะห์ของ {self.agent_id} ไม่พร้อมใช้งานชั่วคราว",
                evidence_refs=(),
                supporting_factors_th=(),
                conflicting_factors_th=(),
                warnings_th=(failure_code,),
                missing_context_th=("PROVIDER_ANALYSIS_UNAVAILABLE",),
                provider_provenance=(
                    execution_provenance.provider_id if execution_provenance is not None else actual_prov
                ),
                execution_provenance=execution_provenance,
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
            "quote": ai_input.quote_context.model_dump(mode="json"),
            "regime": ai_input.structure_context.regime,
            "sessions": list(ai_input.structure_context.current_sessions),
        }


class SMCICTAnalyst(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("smc_ict", "smc_ict.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "internal_state": ai_input.structure_context.internal_state,
            "external_state": ai_input.structure_context.external_state,
            "swings_count": len(ai_input.structure_context.swings),
            "events": [item.model_dump(mode="json") for item in ai_input.structure_context.events[:10]],
            "liquidity": [item.model_dump(mode="json") for item in ai_input.structure_context.liquidity[:10]],
            "zones": [item.model_dump(mode="json") for item in ai_input.structure_context.zones[:10]],
            "dealing_range": (
                ai_input.structure_context.dealing_range.model_dump(mode="json")
                if ai_input.structure_context.dealing_range is not None
                else None
            ),
        }


class MacroNewsAnalyst(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("macro_news", "macro_news.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "news_state": ai_input.news_context.news_state,
            "in_blackout": ai_input.news_context.in_blackout,
            "in_pre_news_window": ai_input.news_context.in_pre_news_window,
            "in_post_news_window": ai_input.news_context.in_post_news_window,
            "news_provenance": {
                "provider": ai_input.provenance.news_provider,
                "revision": ai_input.provenance.news_revision,
            },
        }

    def extract_untrusted_evidence(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "news_events": [event.model_dump(mode="json") for event in ai_input.news_context.events],
        }


class StrategyCritic(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("strategy_critic", "strategy_critic.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "candidate": ai_input.strategy_context.model_dump(
                mode="json",
                include={
                    "availability",
                    "strategy_id",
                    "strategy_version",
                    "direction",
                    "score",
                    "detected_at",
                    "confirmed_at",
                    "status",
                    "unavailable_reason",
                },
            ),
            "plan_summary": {
                "invalidation_th": ai_input.trade_plan_context.invalidation_th,
                "risk_reward_ratio": str(ai_input.trade_plan_context.risk_reward_ratio)
                if ai_input.trade_plan_context.risk_reward_ratio is not None
                else None,
            },
        }


class RiskInterpreter(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("risk_interpreter", "risk_interpreter.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "risk_decision": ai_input.risk_context.model_dump(
                mode="json", exclude={"decision_id", "reservation_id", "account_id", "candidate_id"}
            ),
            "kill_switch_state": ai_input.kill_switch_context.state,
        }


class TradeThesisAgent(BaseAnalyticalAgent):
    def __init__(self):
        super().__init__("trade_thesis", "trade_thesis.v1")

    def extract_context(self, ai_input: AIAnalysisInput) -> dict[str, Any]:
        return {
            "strategy_direction": ai_input.strategy_context.direction,
            "strategy_score": ai_input.strategy_context.score,
            "risk_status": ai_input.risk_context.decision,
            "kill_switch_state": ai_input.kill_switch_context.state,
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


class MetaSynthesisOutput(BaseModel):
    """Strict schema for Meta Controller provider output. Extra fields are strictly forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    directional_bias: DirectionalBias = "NEUTRAL"
    evidence_strength: EvidenceStrength = "MODERATE"
    agent_agreement: AgentAgreement = "LOW"
    summary_th: str = "สรุปผลการวิเคราะห์ภาพรวมโดย AI"
    key_evidence_th: tuple[str, ...] = ()
    conflicts_th: tuple[str, ...] = ()
    risk_notes_th: tuple[str, ...] = ()
    warnings_th: tuple[str, ...] = ()


class MetaController:
    """Synthesizes the six analytical agent results into an executive advisory report."""

    def __init__(self):
        self.agent_id = META_CONTROLLER_ID
        self.prompt_id = "meta_controller.v1"

    async def execute(
        self,
        ai_input: AIAnalysisInput,
        agent_results: dict[str, AgentAnalysisResult],
        provider: ProviderDescriptor,
        config: ModelConfig,
        timeout_seconds: float | None = None,
    ) -> AIAnalysisResult:
        if not isinstance(provider, ProviderDescriptor):
            raise ProviderRequestError(
                f"MetaController.execute requires ProviderDescriptor; "
                f"live {type(provider).__name__} instances are prohibited"
            )
        now_utc = dt.datetime.now(dt.UTC)

        # 1. Compute deterministic agreement and check agent statuses
        biases = [res.directional_bias for res in agent_results.values() if res.status == "READY"]
        agreement = compute_agent_agreement(biases)

        # 2. Prepare meta synthesis payload
        meta_context = {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "risk_decision": ai_input.risk_context.decision,
            "kill_switch_state": ai_input.kill_switch_context.state,
            "agent_agreement": agreement,
            "agent_summaries": {
                aid: {
                    "bias": res.directional_bias,
                    "strength": res.evidence_strength,
                    "status": res.status,
                    "summary_th": res.summary_th,
                }
                for aid, res in agent_results.items()
            },
        }

        structured_payload = build_structured_payload(
            {
                "agent_id": self.agent_id,
                "symbol": ai_input.symbol,
                "as_of": ai_input.as_of.isoformat(),
                "risk_decision_status": ai_input.risk_context.decision,
                "kill_switch_status": ai_input.kill_switch_context.state,
                "agent_agreement": agreement,
                "agent_summaries": meta_context["agent_summaries"],
            },
        )
        system_prompt = get_prompt(self.prompt_id)

        meta_failed = False
        meta_execution_provenance: AIProviderExecutionProvenance | None = None
        try:
            res = await analyze_with_controls(
                provider,
                agent_id=self.agent_id,
                system_prompt=system_prompt,
                user_payload=structured_payload,
                model_config=config,
                timeout_seconds=timeout_seconds,
            )
            raw = dict(res.raw_payload)
            meta_execution_provenance = _execution_provenance(res, config)

            # Strict validation: any forbidden fields (execute, order_type, stop_loss, etc.) fail here
            validated = MetaSynthesisOutput.model_validate(raw)
            bias = validated.directional_bias
            strength = validated.evidence_strength
            summary_th = validated.summary_th
            key_evidence_th = validated.key_evidence_th
            conflicts_th = validated.conflicts_th
            risk_notes_th = validated.risk_notes_th
            warnings_th = validated.warnings_th

        except Exception as exc:
            failure_code = public_provider_failure_code(exc)
            logger.warning(
                "MetaController synthesis failed: provider_id=%s failure_code=%s exception_class=%s",
                provider.provider_id,
                failure_code,
                type(exc).__name__,
            )
            meta_failed = True
            bias = "NEUTRAL"
            strength = "INSUFFICIENT"
            summary_th = "การประมวลผล Meta Controller ไม่พร้อมใช้งานชั่วคราว"
            key_evidence_th = ()
            conflicts_th = ()
            risk_notes_th = ("META_PROVIDER_UNAVAILABLE",)
            warnings_th = (failure_code,)

        # 3. Derive meta status based on agent results AND meta controller health
        ready_count = sum(1 for r in agent_results.values() if r.status == "READY")
        if meta_failed:
            meta_status: MetaStatus = "DEGRADED" if ready_count > 0 else "UNAVAILABLE"
        elif ready_count == 6:
            meta_status = "READY"
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
            "risk_decision_id": ai_input.risk_context.decision_id,
            "input_fingerprint": ai_input.input_fingerprint,
        }
        analysis_fp = fingerprint(semantic_data)

        configured_prov = (
            provider.provider_id
            if isinstance(provider, ProviderDescriptor)
            else getattr(provider, "provider_id", getattr(provider, "provider", "fixture"))
        )
        return AIAnalysisResult(
            analysis_id=ai_input.analysis_id or f"ai_{analysis_fp[:32]}",
            symbol=ai_input.symbol,
            as_of=ai_input.as_of,
            status=meta_status,
            directional_bias=bias,
            evidence_strength=strength,
            agent_agreement=agreement,
            summary_th=summary_th,
            key_evidence_th=key_evidence_th,
            conflicts_th=conflicts_th,
            risk_notes_th=risk_notes_th,
            warnings_th=warnings_th,
            agent_results=agent_results,
            strategy_id=ai_input.strategy_context.strategy_id,
            strategy_version=ai_input.strategy_context.strategy_version,
            risk_decision_id=ai_input.risk_context.decision_id,
            risk_decision_status=ai_input.risk_context.decision,
            kill_switch_state=ai_input.kill_switch_context.state,
            provider_provenance=(
                meta_execution_provenance.provider_id if meta_execution_provenance is not None else configured_prov
            ),
            execution_provenance=meta_execution_provenance,
            prompt_versions=prompt_versions,
            generated_at=now_utc,
            input_fingerprint=ai_input.input_fingerprint,
            analysis_fingerprint=analysis_fp,
            execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
        )
