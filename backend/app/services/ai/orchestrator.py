"""Safety-gated multi-agent AI orchestrator.

Enforces strict authority hierarchy:
Kill Switch > Risk Engine > Strategy Engine > AI Analysis > Human User.

Pre-flight checks short-circuit immediately without calling any AI models when:
1. Kill Switch is ACTIVE (BLOCKED_BY_KILL_SWITCH) or UNKNOWN/malformed (BLOCKED_BY_UPSTREAM)
2. RiskDecision is BLOCKED / unapproved (BLOCKED_BY_RISK) or reservation inactive (BLOCKED_BY_UPSTREAM)
3. Input data is STALE (STALE)
4. No-lookahead violation is detected (BLOCKED_BY_UPSTREAM)
"""

import asyncio
import datetime as dt
import logging
from typing import Any

from app.services.ai.agents import (
    BaseAnalyticalAgent,
    MetaController,
    get_all_analytical_agents,
)
from app.services.ai.domain import (
    AgentAnalysisResult,
    AIAnalysisInput,
    AIAnalysisResult,
    fingerprint,
)
from app.services.ai.provider import AIProvider, FixtureAIProvider, ModelConfig

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS_PER_AGENT = 20000
MAX_PROVIDER_OUTPUT_CHARS = 10000


class AIOrchestrator:
    """Orchestrates the safety-gated execution of the multi-agent AI advisory layer."""

    def __init__(self, provider: AIProvider | None = None, default_config: ModelConfig | None = None):
        self.provider = provider or FixtureAIProvider()
        self.default_config = default_config or ModelConfig()
        self.agents = get_all_analytical_agents()
        self.meta_controller = MetaController()

    @staticmethod
    def _parse_time(val: Any) -> dt.datetime:
        """Parse datetime strictly into UTC datetime; raise ValueError on failure."""
        if isinstance(val, dt.datetime):
            return val if val.tzinfo is not None else val.replace(tzinfo=dt.UTC)
        if isinstance(val, str):
            try:
                return dt.datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception as exc:
                raise ValueError(f"Malformed temporal string: {val}") from exc
        raise ValueError(f"Unparseable temporal type: {type(val).__name__} ({val})")

    @classmethod
    def validate_no_lookahead(cls, ai_input: AIAnalysisInput) -> None:
        """Validate that no information dated after as_of is present in the input.

        Throws ValueError if lookahead leakage or malformed timestamp is detected.
        """
        as_of = ai_input.as_of

        # 1. Market quote timestamp (strict: quote timestamp <= as_of)
        quote_ts = ai_input.quote_context.timestamp
        if quote_ts > as_of:
            raise ValueError(f"No-lookahead violation: quote timestamp ({quote_ts}) is in future of as_of ({as_of})")

        # 2. News context scheduled_at and available_at
        for ev in ai_input.news_context.events:
            if ev.scheduled_at > as_of:
                raise ValueError(f"No-lookahead violation: news scheduled_at ({ev.scheduled_at}) > as_of ({as_of})")
            if ev.available_at > as_of:
                raise ValueError(f"No-lookahead violation: news available_at ({ev.available_at}) > as_of ({as_of})")

        # 3. Market structure timestamps (swings, events, liquidity, zones)
        struct = ai_input.structure_context
        if struct.as_of > as_of:
            raise ValueError(f"No-lookahead violation: structure context as_of ({struct.as_of}) > as_of ({as_of})")

        for swing in struct.swings:
            t = swing.get("time") or swing.get("confirmed_at") or swing.get("timestamp")
            if t is not None:
                parsed_t = cls._parse_time(t)
                if parsed_t > as_of:
                    raise ValueError(f"No-lookahead violation: swing point time ({parsed_t}) > as_of ({as_of})")

        for event in struct.events:
            t = event.get("time") or event.get("created_at") or event.get("timestamp")
            if t is not None:
                parsed_t = cls._parse_time(t)
                if parsed_t > as_of:
                    raise ValueError(f"No-lookahead violation: structure event time ({parsed_t}) > as_of ({as_of})")

        for liq in struct.liquidity:
            t = liq.get("detected_at") or liq.get("time") or liq.get("timestamp")
            if t is not None:
                parsed_t = cls._parse_time(t)
                if parsed_t > as_of:
                    raise ValueError(f"No-lookahead violation: liquidity detected_at ({parsed_t}) > as_of ({as_of})")

        for zone in struct.zones:
            t = zone.get("created_at") or zone.get("time") or zone.get("timestamp")
            if t is not None:
                parsed_t = cls._parse_time(t)
                if parsed_t > as_of:
                    raise ValueError(f"No-lookahead violation: zone created_at ({parsed_t}) > as_of ({as_of})")

        # 4. Strategy candidate timestamps
        strat = ai_input.strategy_context
        if strat.detected_at > as_of:
            raise ValueError(f"No-lookahead violation: candidate detected_at ({strat.detected_at}) > as_of ({as_of})")
        if strat.confirmed_at is not None and strat.confirmed_at > as_of:
            raise ValueError(f"No-lookahead violation: candidate confirmed_at ({strat.confirmed_at}) > as_of ({as_of})")

        for strat_ev in strat.evidence:
            t = strat_ev.get("time") or strat_ev.get("confirmed_at") or strat_ev.get("detected_at")
            if t is not None:
                parsed_t = cls._parse_time(t)
                if parsed_t > as_of:
                    raise ValueError(f"No-lookahead violation: strategy evidence time ({parsed_t}) > as_of ({as_of})")

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
        ks_state = ai_input.kill_switch_context.state.upper()
        if ks_state == "ACTIVE":
            logger.info("AI Analysis blocked: Kill Switch is ACTIVE")
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "KILL_SWITCH_ACTIVE"})
            return AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_ks_{fp[:28]}",
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
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
                risk_decision_status=ai_input.risk_context.decision,
                kill_switch_state="ACTIVE",
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        if ks_state != "INACTIVE":
            logger.info("AI Analysis blocked: Kill Switch state is non-inactive (%s)", ks_state)
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "KILL_SWITCH_UNKNOWN"})
            return AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_ks_{fp[:28]}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="BLOCKED_BY_UPSTREAM",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th=f"ระบบ AI ระงับการให้คำปรึกษาเนื่องจากสถานะ Kill Switch ไม่สมบูรณ์ ({ks_state})",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=(f"สถานะ Kill Switch ไม่ปลอดภัย: {ks_state}",),
                warnings_th=(f"KILL_SWITCH_{ks_state}",),
                agent_results={},
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
                risk_decision_status=ai_input.risk_context.decision,
                kill_switch_state=ks_state,
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        # ---------------------------------------------------------
        # PRE-FLIGHT GATE 2: RISK DECISION & RESERVATION
        # ---------------------------------------------------------
        risk_dec = ai_input.risk_context.decision.upper()
        if risk_dec == "BLOCKED":
            logger.info("AI Analysis blocked: RiskDecision is BLOCKED")
            blocked_reasons = ai_input.risk_context.blocked_reasons_th or ("ความเสี่ยงไม่อนุมัติ",)
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "RISK_BLOCKED"})
            return AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_risk_{fp[:26]}",
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
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
                risk_decision_status="BLOCKED",
                kill_switch_state=ks_state,
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        if risk_dec in ("RISK_NOT_EVALUATED", "NONE", "", "EXPIRED"):
            logger.info("AI Analysis blocked: RiskDecision is not evaluated/expired (%s)", risk_dec)
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "RISK_UNAPPROVED"})
            return AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_risk_{fp[:26]}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="BLOCKED_BY_RISK",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th="ระบบ AI ระงับการวิเคราะห์เนื่องจากยังไม่ผ่านการประเมินความเสี่ยงที่ถูกต้อง",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=(f"Risk decision status: {risk_dec}",),
                warnings_th=(f"RISK_DECISION_{risk_dec}",),
                agent_results={},
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
                risk_decision_status=risk_dec,
                kill_switch_state=ks_state,
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        if risk_dec not in ("APPROVED", "REDUCED"):
            logger.info("AI Analysis blocked: Unknown RiskDecision status (%s)", risk_dec)
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "RISK_UNKNOWN"})
            return AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_risk_{fp[:26]}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="BLOCKED_BY_RISK",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th=f"ระบบ AI ระงับการวิเคราะห์เนื่องจากสถานะความเสี่ยงไม่ถูกต้อง ({risk_dec})",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=(f"Unknown risk decision: {risk_dec}",),
                warnings_th=(f"RISK_DECISION_{risk_dec}",),
                agent_results={},
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
                risk_decision_status=risk_dec,
                kill_switch_state=ks_state,
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        # For APPROVED or REDUCED: must have a valid ACTIVE reservation
        res_status = (ai_input.risk_context.reservation_status or "").upper()
        if res_status != "ACTIVE":
            logger.info("AI Analysis blocked: Risk reservation is not active (%s)", res_status)
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "RESERVATION_INACTIVE"})
            return AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_res_{fp[:26]}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="BLOCKED_BY_UPSTREAM",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th=f"ระบบ AI ระงับการวิเคราะห์เนื่องจากการจองความเสี่ยง (Risk Reservation) ไม่สมบูรณ์ ({res_status})",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=(f"การจองความเสี่ยงไม่อยู่ในสถานะ ACTIVE: {res_status}",),
                warnings_th=(f"RESERVATION_{res_status}",),
                agent_results={},
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
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
        # PRE-FLIGHT GATE 3: STALE / UNAVAILABLE QUOTE
        # ---------------------------------------------------------
        if ai_input.quote_context.is_stale:
            logger.info("AI Analysis blocked: Market quote is STALE")
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "STALE_QUOTE"})
            return AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_stale_{fp[:26]}",
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
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
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
        try:
            self.validate_no_lookahead(ai_input)
        except ValueError as exc:
            logger.info("AI Analysis blocked: No-lookahead violation: %s", exc)
            fp = fingerprint({"symbol": ai_input.symbol, "as_of": as_of.isoformat(), "gate": "LOOKAHEAD_VIOLATION"})
            return AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_lookahead_{fp[:26]}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="BLOCKED_BY_UPSTREAM",
                directional_bias="NO_BIAS",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th="ระบบ AI ระงับการวิเคราะห์เนื่องจากตรวจพบข้อมูลในอนาคต (No-lookahead violation)",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=(f"ละเมิดหลักการ No-Lookahead: {exc}",),
                warnings_th=(str(exc),),
                agent_results={},
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
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
        # EXECUTE EXACTLY SIX ANALYTICAL AGENTS CONCURRENTLY
        # ENFORCE HARD ORCHESTRATOR TIMEOUTS AND CANCEL HANGING CALLS
        # ---------------------------------------------------------
        async def _run_agent_with_hard_timeout(agent: BaseAnalyticalAgent) -> AgentAnalysisResult:
            timeout = effective_config.timeout_seconds
            try:
                return await asyncio.wait_for(
                    agent.execute(ai_input, self.provider, effective_config, timeout_seconds=timeout),
                    timeout=timeout,
                )
            except TimeoutError:
                logger.warning("Agent %s timed out after %s seconds (hard cancel)", agent.agent_id, timeout)
                return AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="DEGRADED",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th=f"การวิเคราะห์ของ {agent.agent_id} เกินกำหนดเวลา timeout ({timeout}s)",
                    warnings_th=(f"Hard timeout after {timeout}s",),
                    missing_context_th=(f"Agent timeout after {timeout}s",),
                    provider_provenance=effective_config.provider,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )
            except Exception as exc:
                logger.warning("Agent %s execution raised unhandled exception: %s", agent.agent_id, exc)
                return AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="DEGRADED",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th=f"การวิเคราะห์ของ {agent.agent_id} เกิดข้อผิดพลาด: {exc}",
                    warnings_th=(str(exc),),
                    missing_context_th=(str(exc),),
                    provider_provenance=effective_config.provider,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )

        tasks = [_run_agent_with_hard_timeout(agent) for agent in self.agents]
        results_list = await asyncio.gather(*tasks)
        agent_results_map = {res.agent_id: res for res in results_list}

        # ---------------------------------------------------------
        # EXECUTE META CONTROLLER WITH HARD TIMEOUT
        # ---------------------------------------------------------
        meta_timeout = effective_config.timeout_seconds
        try:
            meta_result = await asyncio.wait_for(
                self.meta_controller.execute(
                    ai_input=ai_input,
                    agent_results=agent_results_map,
                    provider=self.provider,
                    config=effective_config,
                    timeout_seconds=meta_timeout,
                ),
                timeout=meta_timeout,
            )
        except TimeoutError:
            logger.warning("MetaController timed out after %s seconds (hard cancel)", meta_timeout)
            meta_result = AIAnalysisResult(
                analysis_id=ai_input.analysis_id or f"ai_meta_to_{now_utc.timestamp()}",
                symbol=ai_input.symbol,
                as_of=as_of,
                status="DEGRADED",
                directional_bias="NEUTRAL",
                evidence_strength="INSUFFICIENT",
                agent_agreement="UNAVAILABLE",
                summary_th=f"Meta Controller เกินกำหนดเวลา timeout ({meta_timeout}s)",
                key_evidence_th=(),
                conflicts_th=(),
                risk_notes_th=("Meta Controller timeout",),
                warnings_th=(f"MetaController hard timeout after {meta_timeout}s",),
                agent_results=agent_results_map,
                strategy_id=ai_input.strategy_context.strategy_id,
                strategy_version=ai_input.strategy_context.strategy_version,
                risk_decision_id=ai_input.risk_context.decision_id,
                risk_decision_status=ai_input.risk_context.decision,
                kill_switch_state=ks_state,
                provider_provenance=effective_config.provider,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fingerprint({"symbol": ai_input.symbol, "status": "DEGRADED"}),
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        return meta_result


# Singleton instance for default usage
ai_orchestrator = AIOrchestrator()
