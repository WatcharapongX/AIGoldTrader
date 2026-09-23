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
    compute_agent_agreement,
    get_all_analytical_agents,
)
from app.services.ai.budget import AnalysisBudget, AnalysisBudgetLimits, AnalysisReservation
from app.services.ai.domain import (
    AgentAnalysisResult,
    AIAnalysisInput,
    AIAnalysisResult,
    fingerprint,
)
from app.services.ai.provider import (
    ModelBinding,
    ModelConfig,
    ProviderAuthError,
    ProviderCapacityExhausted,
    ProviderDescriptor,
    public_provider_failure_code,
)

logger = logging.getLogger(__name__)


class AIOrchestrator:
    """Orchestrates the safety-gated execution of the multi-agent AI advisory layer."""

    def __init__(
        self,
        provider: ProviderDescriptor | None = None,
        default_config: ModelConfig | None = None,
        descriptor: ProviderDescriptor | None = None,
        budget_limits: AnalysisBudgetLimits | None = None,
    ):
        from app.core.config import get_settings

        settings = get_settings()
        target_provider: ProviderDescriptor
        if descriptor is not None:
            if not isinstance(descriptor, ProviderDescriptor):
                d_name = type(descriptor).__name__
                raise ValueError(f"AIOrchestrator requires ProviderDescriptor; live {d_name} instances are prohibited")
            target_provider = descriptor
        elif provider is not None:
            if not isinstance(provider, ProviderDescriptor):
                p_name = type(provider).__name__
                raise ValueError(f"AIOrchestrator requires ProviderDescriptor; live {p_name} instances are prohibited")
            target_provider = provider
        else:
            mode = getattr(settings, "ai_provider_mode", "fixture")
            p_type = getattr(settings, "ai_provider_type", "fixture")
            if mode == "external":
                if p_type == "fixture":
                    raise ValueError(
                        "Invalid configuration: ai_provider_mode='external' cannot use ai_provider_type='fixture'"
                    )
                target_provider = ProviderDescriptor(
                    provider_id="configured_external",
                    provider_type="openai_compatible",
                    config_profile="primary",
                    model_bindings=tuple(
                        ModelBinding(alias=alias, model=model)
                        for alias, model in getattr(settings, "ai_model_mapping", {}).items()
                    ),
                )
            else:
                target_provider = ProviderDescriptor(
                    provider_id="default_fixture",
                    provider_type="fixture",
                    config_profile="fixture",
                )
        self.provider: ProviderDescriptor = target_provider

        prov_name = self.provider.provider_id
        self.default_config = default_config or ModelConfig(provider=prov_name)
        self.budget_limits = budget_limits or AnalysisBudgetLimits(
            max_provider_attempts=settings.ai_analysis_max_provider_attempts,
            max_prompt_tokens=settings.ai_analysis_max_prompt_tokens,
            max_completion_tokens=settings.ai_analysis_max_completion_tokens,
            max_total_tokens=settings.ai_analysis_max_total_tokens,
            max_measured_bytes=settings.ai_analysis_max_measured_bytes,
            deadline_seconds=settings.ai_analysis_deadline_seconds,
        )
        self.agents = get_all_analytical_agents()
        self.meta_controller = MetaController()

    def _resource_controlled_agent_result(
        self,
        ai_input: AIAnalysisInput,
        agent: BaseAnalyticalAgent,
        warning: str,
    ) -> AgentAnalysisResult:
        return AgentAnalysisResult(
            agent_id=agent.agent_id,
            agent_version="ai-1.0.0",
            status="UNAVAILABLE",
            directional_bias="NO_BIAS",
            evidence_strength="INSUFFICIENT",
            summary_th=f"การวิเคราะห์ของ {agent.agent_id} ไม่พร้อมใช้งานภายใต้ขีดจำกัดของคำขอนี้",
            warnings_th=(warning,),
            missing_context_th=(warning,),
            provider_provenance=self.provider.provider_id,
            prompt_version=agent.prompt_id,
            generated_at=dt.datetime.now(dt.UTC),
            as_of=ai_input.as_of,
            token_usage=None,
        )

    def _meta_not_executed_result(
        self,
        ai_input: AIAnalysisInput,
        agent_results: dict[str, AgentAnalysisResult],
        warning: str,
    ) -> AIAnalysisResult:
        """Build a truthful server envelope without claiming provider synthesis."""
        ready_count = sum(result.status == "READY" for result in agent_results.values())
        status = "DEGRADED" if ready_count else "UNAVAILABLE"
        agreement = compute_agent_agreement(
            [result.directional_bias for result in agent_results.values() if result.status == "READY"]
        )
        semantic_data = {
            "symbol": ai_input.symbol,
            "as_of": ai_input.as_of.isoformat(),
            "status": status,
            "warning": warning,
            "agent_biases": {key: value.directional_bias for key, value in sorted(agent_results.items())},
            "input_fingerprint": ai_input.input_fingerprint,
        }
        analysis_fp = fingerprint(semantic_data)
        return AIAnalysisResult(
            analysis_id=ai_input.analysis_id or f"ai_{analysis_fp[:32]}",
            symbol=ai_input.symbol,
            as_of=ai_input.as_of,
            status=status,
            directional_bias="NEUTRAL",
            evidence_strength="INSUFFICIENT",
            agent_agreement=agreement,
            summary_th="Meta Controller ไม่ได้ทำงานเนื่องจากขีดจำกัดทรัพยากรของคำขอ",
            key_evidence_th=(),
            conflicts_th=(),
            risk_notes_th=("META_CONTROLLER_NOT_EXECUTED",),
            warnings_th=(warning,),
            agent_results=agent_results,
            strategy_id=ai_input.strategy_context.strategy_id,
            strategy_version=ai_input.strategy_context.strategy_version,
            risk_decision_id=ai_input.risk_context.decision_id,
            risk_decision_status=ai_input.risk_context.decision,
            kill_switch_state=ai_input.kill_switch_context.state,
            provider_provenance=self.provider.provider_id,
            execution_provenance=None,
            prompt_versions={result.agent_id: result.prompt_version for result in agent_results.values()},
            generated_at=dt.datetime.now(dt.UTC),
            input_fingerprint=ai_input.input_fingerprint,
            analysis_fingerprint=analysis_fp,
            execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
        )

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
        actual_provenance = self.provider.provider_id

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
                provider_provenance=actual_provenance,
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
                provider_provenance=actual_provenance,
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
                provider_provenance=actual_provenance,
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
                provider_provenance=actual_provenance,
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
                provider_provenance=actual_provenance,
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
                provider_provenance=actual_provenance,
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
                provider_provenance=actual_provenance,
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
                provider_provenance=actual_provenance,
                prompt_versions={},
                generated_at=now_utc,
                input_fingerprint=ai_input.input_fingerprint,
                analysis_fingerprint=fp,
                execution_disclaimer="ADVISORY_ONLY_NO_EXECUTION_AUTHORITY",
            )

        # All authority gates have passed. Start the request-scoped monotonic
        # deadline here so blocked requests consume no AI runtime budget.
        budget = AnalysisBudget(self.budget_limits)

        # Deterministically pre-reserve in canonical agent order. Coroutines never
        # race for the final aggregate slot, but funded agents still run concurrently.
        agent_results_map: dict[str, AgentAnalysisResult] = {}
        base_funded: list[tuple[BaseAnalyticalAgent, AnalysisReservation]] = []
        base_config = effective_config.model_copy(update={"max_retries": 0})
        for agent in self.agents:
            if agent.agent_id == "macro_news" and ai_input.news_context.availability != "AVAILABLE":
                agent_results_map[agent.agent_id] = AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="UNAVAILABLE",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th="ไม่มีบริบทข่าวที่มีแหล่งที่มาและเวลาอ้างอิงที่ตรวจสอบได้",
                    warnings_th=("AUTHORITATIVE_NEWS_UNAVAILABLE",),
                    missing_context_th=(ai_input.news_context.unavailable_reason or "News authority unavailable",),
                    provider_provenance=actual_provenance,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )
                continue
            reservation = await budget.reserve(agent.agent_id, base_config)
            if reservation is None:
                warning = (
                    "ANALYSIS_DEADLINE_EXHAUSTED"
                    if budget.deadline_remaining() <= 0
                    else "ANALYSIS_BUDGET_EXHAUSTED"
                )
                agent_results_map[agent.agent_id] = self._resource_controlled_agent_result(
                    ai_input, agent, warning
                )
                continue
            base_funded.append((agent, reservation))

        # Only after every eligible agent has had a canonical chance at its base
        # attempt are optional retries distributed in stable canonical rounds.
        for _ in range(effective_config.max_retries):
            for _, reservation in base_funded:
                await budget.authorize_additional_attempt(reservation, effective_config)
        funded = [
            (
                agent,
                reservation,
                effective_config.model_copy(
                    update={"max_retries": reservation.authorized_attempts - 1}
                ),
            )
            for agent, reservation in base_funded
        ]

        # ---------------------------------------------------------
        # EXECUTE FUNDED ANALYTICAL AGENTS CONCURRENTLY
        # ---------------------------------------------------------
        async def _run_agent_with_hard_timeout(
            agent: BaseAnalyticalAgent,
            reservation: AnalysisReservation,
            bounded_config: ModelConfig,
        ) -> AgentAnalysisResult:
            timeout = min(bounded_config.timeout_seconds, reservation.deadline_remaining())
            try:
                return await agent.execute(
                    ai_input,
                    self.provider,
                    bounded_config,
                    timeout_seconds=timeout,
                    analysis_reservation=reservation,
                )
            except asyncio.CancelledError:
                await reservation.reconcile_failure()
                raise
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
                    provider_provenance=actual_provenance,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )
            except ProviderCapacityExhausted as exc:
                failure_code = public_provider_failure_code(exc)
                logger.warning(
                    "Agent provider capacity exhausted: agent_id=%s failure_code=%s exception_class=%s",
                    agent.agent_id,
                    failure_code,
                    type(exc).__name__,
                )
                return AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="UNAVAILABLE",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th="ระบบ AI ไม่สามารถประมวลผลได้เนื่องจากคิว Provider เต็ม (Capacity Exhausted)",
                    warnings_th=(failure_code,),
                    missing_context_th=("PROVIDER_ANALYSIS_UNAVAILABLE",),
                    provider_provenance=actual_provenance,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )
            except ProviderAuthError as exc:
                failure_code = public_provider_failure_code(exc)
                logger.warning(
                    "Agent provider authentication failed: agent_id=%s failure_code=%s exception_class=%s",
                    agent.agent_id,
                    failure_code,
                    type(exc).__name__,
                )
                return AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="UNAVAILABLE",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th="ระบบ AI ไม่สามารถประมวลผลได้เนื่องจากปัญหาการยืนยันตัวตน Provider (Auth Error)",
                    warnings_th=(failure_code,),
                    missing_context_th=("PROVIDER_ANALYSIS_UNAVAILABLE",),
                    provider_provenance=actual_provenance,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )
            except Exception as exc:
                failure_code = public_provider_failure_code(exc)
                logger.warning(
                    "Agent execution raised unhandled exception: agent_id=%s failure_code=%s exception_class=%s",
                    agent.agent_id,
                    failure_code,
                    type(exc).__name__,
                )
                return AgentAnalysisResult(
                    agent_id=agent.agent_id,
                    agent_version="ai-1.0.0",
                    status="DEGRADED",
                    directional_bias="NO_BIAS",
                    evidence_strength="INSUFFICIENT",
                    summary_th=f"การวิเคราะห์ของ {agent.agent_id} ไม่พร้อมใช้งานชั่วคราว",
                    warnings_th=(failure_code,),
                    missing_context_th=("PROVIDER_ANALYSIS_UNAVAILABLE",),
                    provider_provenance=actual_provenance,
                    prompt_version=agent.prompt_id,
                    generated_at=dt.datetime.now(dt.UTC),
                    as_of=as_of,
                    token_usage=None,
                )
            finally:
                if not reservation.terminal:
                    await reservation.reconcile_failure()

        task_pairs = [
            (
                agent,
                asyncio.create_task(_run_agent_with_hard_timeout(agent, reservation, bounded_config)),
            )
            for agent, reservation, bounded_config in funded
        ]
        if task_pairs:
            all_tasks = [task for _, task in task_pairs]
            try:
                _, pending = await asyncio.wait(
                    all_tasks,
                    timeout=budget.deadline_remaining(),
                )
            except asyncio.CancelledError:
                for task in all_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*all_tasks, return_exceptions=True)
                raise
            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            for agent, task in task_pairs:
                if task.cancelled():
                    agent_results_map[agent.agent_id] = self._resource_controlled_agent_result(
                        ai_input, agent, "ANALYSIS_DEADLINE_EXHAUSTED"
                    )
                else:
                    agent_results_map[agent.agent_id] = task.result()

        # Restore canonical order regardless of completion order.
        agent_results_map = {
            agent.agent_id: agent_results_map[agent.agent_id] for agent in self.agents
        }

        # ---------------------------------------------------------
        # EXECUTE META CONTROLLER ONLY WITH A FRESH AGGREGATE RESERVATION
        # ---------------------------------------------------------
        meta_reservation = await budget.reserve(self.meta_controller.agent_id, effective_config)
        if meta_reservation is None:
            warning = (
                "ANALYSIS_DEADLINE_EXHAUSTED"
                if budget.deadline_remaining() <= 0
                else "ANALYSIS_BUDGET_EXHAUSTED"
            )
            return self._meta_not_executed_result(ai_input, agent_results_map, warning)

        meta_config = effective_config.model_copy(
            update={"max_retries": meta_reservation.authorized_attempts - 1}
        )
        meta_timeout = min(meta_config.timeout_seconds, meta_reservation.deadline_remaining())
        try:
            meta_result = await asyncio.wait_for(
                self.meta_controller.execute(
                    ai_input=ai_input,
                    agent_results=agent_results_map,
                    provider=self.provider,
                    config=meta_config,
                    timeout_seconds=meta_timeout,
                    analysis_reservation=meta_reservation,
                ),
                timeout=meta_reservation.deadline_remaining(),
            )
        except TimeoutError:
            await meta_reservation.reconcile_failure()
            return self._meta_not_executed_result(
                ai_input, agent_results_map, "ANALYSIS_DEADLINE_EXHAUSTED"
            )
        except asyncio.CancelledError:
            await meta_reservation.reconcile_failure()
            raise
        finally:
            if not meta_reservation.terminal:
                await meta_reservation.reconcile_failure()

        return meta_result


# Singleton instance for default usage
ai_orchestrator = AIOrchestrator()
