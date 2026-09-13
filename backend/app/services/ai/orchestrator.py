"""Safety-gated multi-agent AI orchestrator.

Enforces strict authority hierarchy:
Kill Switch > Risk Engine > Strategy Engine > AI Analysis > Human User.

Pre-flight checks short-circuit immediately without calling any AI models when:
1. Kill Switch is ACTIVE (BLOCKED_BY_KILL_SWITCH)
2. RiskDecision is BLOCKED (BLOCKED_BY_RISK)
3. Input data is STALE or missing (STALE / BLOCKED_BY_UPSTREAM)
4. No-lookahead violation is detected (available_at > as_of)
"""

import asyncio
import datetime as dt
import logging

from app.services.ai.agents import (
    MetaController,
    get_all_analytical_agents,
)
from app.services.ai.domain import (
    AIAnalysisInput,
    AIAnalysisResult,
    fingerprint,
)
from app.services.ai.provider import AIProvider, FixtureAIProvider, ModelConfig

logger = logging.getLogger(__name__)


class AIOrchestrator:
    """Orchestrates the safety-gated execution of the multi-agent AI advisory layer."""

    def __init__(self, provider: AIProvider | None = None, default_config: ModelConfig | None = None):
        self.provider = provider or FixtureAIProvider()
        self.default_config = default_config or ModelConfig()
        self.agents = get_all_analytical_agents()
        self.meta_controller = MetaController()

    @staticmethod
    def validate_no_lookahead(ai_input: AIAnalysisInput) -> None:
        """Validate that no information dated after as_of is present in the input.

        Throws ValueError if lookahead leakage is detected.
        """
        as_of = ai_input.as_of

        # Check news context events
        news = ai_input.news_context
        if isinstance(news, dict):
            events = news.get("events") or news.get("event_vintages") or []
            if isinstance(events, list):
                for ev in events:
                    if isinstance(ev, dict):
                        avail = ev.get("available_at")
                        if avail is not None:
                            if isinstance(avail, str):
                                avail_dt = dt.datetime.fromisoformat(avail.replace("Z", "+00:00"))
                            elif isinstance(avail, dt.datetime):
                                avail_dt = avail
                            else:
                                continue
                            if avail_dt > as_of:
                                raise ValueError(
                                    f"No-lookahead violation: news event available_at ({avail_dt}) "
                                    f"is after as_of ({as_of})"
                                )

        # Check market quote timestamp
        quote = ai_input.market_quote
        if isinstance(quote, dict):
            quote_ts = quote.get("timestamp")
            if quote_ts is not None:
                if isinstance(quote_ts, str):
                    q_dt = dt.datetime.fromisoformat(quote_ts.replace("Z", "+00:00"))
                elif isinstance(quote_ts, dt.datetime):
                    q_dt = quote_ts
                else:
                    q_dt = None
                if q_dt and q_dt > as_of + dt.timedelta(seconds=5):
                    raise ValueError(
                        f"No-lookahead violation: quote timestamp ({q_dt}) is in future of as_of ({as_of})"
                    )

    async def analyze(
        self,
        ai_input: AIAnalysisInput,
        config: ModelConfig | None = None,
    ) -> AIAnalysisResult:
        """Run the full safety-gated AI analysis workflow."""
        effective_config = config or self.default_config
        now_utc = dt.datetime.now(dt.UTC)
        as_of = ai_input.as_of

        # ---------------------------------------------------------
        # PRE-FLIGHT GATE 1: KILL SWITCH
        # ---------------------------------------------------------
        ks_state = str(ai_input.kill_switch_state.get("state", "INACTIVE")).upper()
        if ks_state == "ACTIVE":
            logger.info("AI Analysis blocked: Kill Switch is ACTIVE")
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "KILL_SWITCH_ACTIVE"})
            return AIAnalysisResult(
                analysis_id=f"ai_ks_{fp[:28]}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="BLOCKED_BY_KILL_SWITCH",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th="ระบบ AI ระงับการให้คำปรึกษาเนื่องจาก Kill Switch กำลังทำงาน (ACTIVE)",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=("Kill Switch ACTIVE - การวิเคราะห์ทั้งหมดถูกระงับเพื่อความปลอดภัยสูงสุด",),
                warnings_th=("KILL_SWITCH_ACTIVE",),
                agent_results={},
                strategy_id=str(ai_input.strategy_candidate.get("strategy_id", "")),
                strategy_version=str(ai_input.strategy_candidate.get("strategy_version", "")),
                risk_decision_id=str(ai_input.risk_decision.get("id", "")),
                risk_decision_status=str(ai_input.risk_decision.get("decision", "")),
                kill_switch_state="ACTIVE",
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        # ---------------------------------------------------------
        # PRE-FLIGHT GATE 2: RISK DECISION BLOCKED
        # ---------------------------------------------------------
        risk_dec = str(ai_input.risk_decision.get("decision", "APPROVED")).upper()
        if risk_dec == "BLOCKED":
            logger.info("AI Analysis blocked: RiskDecision is BLOCKED")
            blocked_reasons = tuple(
                str(r) for r in ai_input.risk_decision.get("blocked_reasons_th", ["ความเสี่ยงไม่อนุมัติ"])
            )
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "RISK_BLOCKED"})
            return AIAnalysisResult(
                analysis_id=f"ai_risk_{fp[:26]}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="BLOCKED_BY_RISK",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th="ระบบ AI ระงับการวิเคราะห์เชิงรุกเนื่องจากการประเมินความเสี่ยงไม่อนุมัติ (BLOCKED)",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=blocked_reasons,
                warnings_th=("RISK_DECISION_BLOCKED",),
                agent_results={},
                strategy_id=str(ai_input.strategy_candidate.get("strategy_id", "")),
                strategy_version=str(ai_input.strategy_candidate.get("strategy_version", "")),
                risk_decision_id=str(ai_input.risk_decision.get("id", "")),
                risk_decision_status="BLOCKED",
                kill_switch_state=ks_state,
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        # ---------------------------------------------------------
        # PRE-FLIGHT GATE 3: STALE / UNAVAILABLE UPSTREAM
        # ---------------------------------------------------------
        quote = ai_input.market_quote
        is_quote_stale = bool(quote.get("is_stale", False))
        if is_quote_stale:
            logger.info("AI Analysis blocked: Market quote is STALE")
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "STALE_QUOTE"})
            return AIAnalysisResult(
                analysis_id=f"ai_stale_{fp[:26]}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="STALE",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th="ระบบ AI ระงับการวิเคราะห์เนื่องจากข้อมูลราคาตลาดหมดอายุ (Stale Quote)",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=("ราคาตลาดขาดความสดใหม่ ไม่ปลอดภัยสำหรับการวิเคราะห์",),
                warnings_th=("STALE_MARKET_DATA",),
                agent_results={},
                strategy_id=str(ai_input.strategy_candidate.get("strategy_id", "")),
                strategy_version=str(ai_input.strategy_candidate.get("strategy_version", "")),
                risk_decision_id=str(ai_input.risk_decision.get("id", "")),
                risk_decision_status=risk_dec,
                kill_switch_state=ks_state,
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        # ---------------------------------------------------------
        # PRE-FLIGHT GATE 4: NO-LOOKAHEAD VALIDATION
        # ---------------------------------------------------------
        self.validate_no_lookahead(ai_input)

        # ---------------------------------------------------------
        # EXECUTE EXACTLY SIX ANALYTICAL AGENTS CONCURRENTLY
        # ---------------------------------------------------------
        tasks = [
            agent.execute(ai_input, self.provider, effective_config, timeout_seconds=effective_config.timeout_seconds)
            for agent in self.agents
        ]
        results_list = await asyncio.gather(*tasks)

        agent_results_map = {res.agent_id: res for res in results_list}

        # ---------------------------------------------------------
        # EXECUTE META CONTROLLER
        # ---------------------------------------------------------
        meta_result = await self.meta_controller.execute(
            ai_input=ai_input,
            agent_results=agent_results_map,
            provider=self.provider,
            config=effective_config,
            timeout_seconds=effective_config.timeout_seconds,
        )

        return meta_result


# Singleton instance for default usage
ai_orchestrator = AIOrchestrator()
