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
from app.services.ai.provider import (
    AIProvider,
    ModelConfig,
    ProviderAuthError,
    ProviderCapacityExhausted,
    ProviderDescriptor,
)

logger = logging.getLogger(__name__)


class AIOrchestrator:
    """Orchestrates the safety-gated execution of the multi-agent AI advisory layer."""

    def __init__(
        self,
        provider: AIProvider | ProviderDescriptor | None = None,
        default_config: ModelConfig | None = None,
        descriptor: ProviderDescriptor | None = None,
    ):
        from app.core.config import get_settings

        settings = get_settings()
        target_provider: AIProvider | ProviderDescriptor
        if descriptor is not None:
            target_provider = descriptor
        elif provider is not None:
            target_provider = provider
        else:
            if getattr(settings, "ai_provider_mode", "fixture") == "external":
                target_provider = ProviderDescriptor(
                    provider_id="configured_external",
                    provider_type=getattr(settings, "ai_provider_type", "openai_compatible"),
                    credential_ref="AI_PROVIDER_API_KEY",
                    base_url_ref="AI_PROVIDER_BASE_URL",
                )
            else:
                target_provider = ProviderDescriptor(
                    provider_id="default_fixture",
                    provider_type="fixture",
                )
        self.provider: AIProvider | ProviderDescriptor = target_provider

        prov_name = (
            self.provider.provider_type
            if isinstance(self.provider, ProviderDescriptor)
            else getattr(self.provider, "provider", "fixture")
        )
        self.default_config = default_config or ModelConfig(provider=prov_name)
        self.agents = get_all_analytical_agents()
        self.meta_controller = MetaController()

    @classmethod
    def validate_no_lookahead(cls, ai_input: AIAnalysisInput) -> None:
        """Validate that no information dated after as_of is present in the input.

        Throws ValueError if lookahead leakage or malformed timestamp is detected.
        """
        as_of = ai_input.as_of

        def reject_future(label: str, *values: dt.datetime | None) -> None:
            for value in values:
                if value is not None and value > as_of:
                    raise ValueError(f"No-lookahead violation: {label} ({value}) > as_of ({as_of})")

        quote = ai_input.quote_context
        if quote.availability == "UNAVAILABLE" or quote.timestamp is None:
            raise ValueError("Authoritative market quote unavailable")
        reject_future("quote timestamp", quote.timestamp)

        structure = ai_input.structure_context
        if structure.availability != "AVAILABLE" or structure.as_of is None:
            raise ValueError("Authoritative market structure unavailable")
        reject_future("structure as_of", structure.as_of)
        for swing in structure.swings:
            reject_future("swing", swing.swing_time, swing.confirmed_at)
        for event in structure.events:
            reject_future(
                "structure event",
                event.swing_time,
                event.occurred_at,
                event.created_at,
                event.detected_at,
                event.confirmed_at,
                event.available_at,
            )
        for liquidity in structure.liquidity:
            reject_future(
                "liquidity",
                liquidity.created_at,
                liquidity.detected_at,
                liquidity.confirmed_at,
                liquidity.swept_at,
                liquidity.ended_at,
            )
        for zone in structure.zones:
            reject_future("zone", zone.occurred_at, zone.created_at, zone.confirmed_at, zone.ended_at)
        if structure.dealing_range is not None:
            reject_future(
                "dealing range",
                structure.dealing_range.origin_time,
                structure.dealing_range.confirmed_at,
            )

        news = ai_input.news_context
        if news.availability == "AVAILABLE":
            reject_future("news context as_of", news.as_of)
            for news_event in news.events:
                reject_future(
                    "news event",
                    news_event.scheduled_at,
                    news_event.available_at,
                    news_event.updated_at,
                    news_event.released_at,
                )
        elif ai_input.strategy_context.strategy_id in ("STRAT05", "STRAT06"):
            raise ValueError("Authoritative news is required for this strategy")

        strategy = ai_input.strategy_context
        if strategy.availability != "AVAILABLE" or strategy.detected_at is None:
            raise ValueError("Authoritative strategy candidate unavailable")
        reject_future("candidate", strategy.detected_at, strategy.confirmed_at)
        for evidence in strategy.evidence:
            reject_future(
                "strategy evidence",
                evidence.created_at,
                evidence.detected_at,
                evidence.confirmed_at,
                evidence.available_at,
            )

        plan = ai_input.trade_plan_context
        if plan.availability != "AVAILABLE" or plan.as_of is None or plan.expires_at is None:
            raise ValueError("Authoritative TradePlan unavailable")
        reject_future("trade plan", plan.as_of, plan.created_at)
        if plan.expires_at <= as_of:
            raise ValueError("TradePlan has expired")
        for evidence in plan.evidence:
            reject_future(
                "trade plan evidence",
                evidence.created_at,
                evidence.detected_at,
                evidence.confirmed_at,
                evidence.available_at,
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
        if ai_input.quote_context.availability == "STALE" or ai_input.quote_context.is_stale:
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
            if agent.agent_id == "macro_news" and ai_input.news_context.availability != "AVAILABLE":
                return AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="UNAVAILABLE",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th="ไม่มีบริบทข่าวที่มีแหล่งที่มาและเวลาอ้างอิงที่ตรวจสอบได้",
                    warnings_th=("AUTHORITATIVE_NEWS_UNAVAILABLE",),
                    missing_context_th=(ai_input.news_context.unavailable_reason or "News authority unavailable",),
                    provider_provenance=effective_config.provider,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )
            try:
                return await agent.execute(ai_input, self.provider, effective_config, timeout_seconds=timeout)
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
            except ProviderCapacityExhausted as exc:
                logger.warning("Agent %s provider capacity exhausted: %s", agent.agent_id, exc)
                return AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="UNAVAILABLE",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th="ระบบ AI ไม่สามารถประมวลผลได้เนื่องจากคิว Provider เต็ม (Capacity Exhausted)",
                    warnings_th=("PROVIDER_CAPACITY_EXHAUSTED", str(exc)),
                    missing_context_th=(str(exc),),
                    provider_provenance=effective_config.provider,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )
            except ProviderAuthError as exc:
                logger.warning("Agent %s provider auth failed: %s", agent.agent_id, exc)
                return AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="UNAVAILABLE",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th="ระบบ AI ไม่สามารถประมวลผลได้เนื่องจากปัญหาการยืนยันตัวตน Provider (Auth Error)",
                    warnings_th=("PROVIDER_AUTH_ERROR", str(exc)),
                    missing_context_th=(str(exc),),
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
            meta_result = await self.meta_controller.execute(
                ai_input=ai_input,
                agent_results=agent_results_map,
                provider=self.provider,
                config=effective_config,
                timeout_seconds=meta_timeout,
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
