"""Six transparent playbooks; mandatory conditions precede scoring and structural geometry."""

import datetime as dt
from collections import OrderedDict
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal, cast

from app.services.analysis.domain import StructureEvent
from app.services.market_data.domain import SECONDS
from app.services.strategy.domain import (
    EVALUATION_VERSION,
    Evaluation,
    Evidence,
    NewsCandidateProvenance,
    SetupCandidate,
    StrategyConfig,
    StrategyDefinition,
    StrategyMarketContext,
    Target,
    TradePlanSuggestion,
    TraderProfile,
    fingerprint,
)

D = Decimal
STYLES: tuple[Literal["SCALP", "DAY_TRADE", "SWING", "RUN_TREND"], ...] = ("SCALP", "DAY_TRADE", "SWING", "RUN_TREND")
DEFINITIONS = (
    StrategyDefinition(
        id="STRAT01",
        name="SMC Liquidity Reversal",
        category="SMC_LIQUIDITY",
        styles=STYLES,
        required_context=("HTF", "SWEEP", "MSS_CHOCH", "FVG_OB", "RETEST"),
        description_th="กวาดสภาพคล่อง กลับเข้าระดับเดิม เปลี่ยนโครงสร้าง และย่อทดสอบโซน",
    ),
    StrategyDefinition(
        id="STRAT02",
        name="Trend Pullback",
        category="TREND_PULLBACK",
        styles=STYLES,
        required_context=("HTF_TREND", "BOS", "PULLBACK_ZONE", "LTF_CONFIRMATION"),
        description_th="ตามแนวโน้มใหญ่ รอย่อเข้าโซนและยืนยันโครงสร้างกรอบเล็ก",
    ),
    StrategyDefinition(
        id="STRAT03",
        name="Breakout Retest",
        category="BREAKOUT_PATTERN",
        styles=STYLES,
        required_context=("CONFIRMED_PATTERN", "CLOSE_BREAK", "DISPLACEMENT", "RETEST", "STRUCTURE"),
        description_th="ราคาปิดทะลุกรอบหรือรูปแบบ ตามด้วยการกลับทดสอบและยืนยันโครงสร้าง",
    ),
    StrategyDefinition(
        id="STRAT04",
        name="Range Mean Reversion",
        category="MEAN_REVERSION",
        styles=STYLES,
        required_context=("RANGING", "BOUNDARIES", "REJECTION", "STRUCTURE"),
        description_th="กลับเข้ากรอบจากขอบราคา ใช้ได้เมื่อไม่มีแนวโน้มแรง",
    ),
    StrategyDefinition(
        id="STRAT05",
        name="Post-News Momentum",
        category="NEWS_MOMENTUM",
        styles=STYLES,
        required_context=("NEWS", "RELEASED_ACTUAL", "MACRO_ALIGNMENT", "REACTION", "SPREAD", "STRUCTURE"),
        description_th="ติดตามแรงหลังประกาศจริง เมื่อข่าว ราคา และโครงสร้างสอดคล้องกัน",
    ),
    StrategyDefinition(
        id="STRAT06",
        name="Post-News Liquidity Reversal",
        category="NEWS_REVERSAL",
        styles=STYLES,
        required_context=("NEWS", "HIGH_IMPACT_RELEASE", "SWEEP_RECLAIM", "MSS_CHOCH", "SPREAD"),
        description_th="หลังข่าวแรง รอกวาดราคาและกลับเข้าระดับเดิมพร้อมยืนยันการกลับตัว",
    ),
)


def profiles(config: StrategyConfig, config_id: str) -> tuple[TraderProfile, ...]:
    choices = (
        ("research", "Strategy Lab", "DAY_TRADE", tuple(d.id for d in DEFINITIONS)),
        ("smc", "SMC Specialist", "SCALP", ("STRAT01",)),
        ("trend", "Trend Runner", "RUN_TREND", ("STRAT02",)),
        ("liquidity", "Liquidity Specialist", "SWING", ("STRAT01",)),
        ("breakout", "Breakout Trader", "DAY_TRADE", ("STRAT03",)),
        ("range", "Range Trader", "SCALP", ("STRAT04",)),
        ("news", "News Trader", "DAY_TRADE", ("STRAT05", "STRAT06")),
    )
    return tuple(
        TraderProfile.model_validate(
            dict(
                id=name,
                name=title,
                description_th="โปรไฟล์วิเคราะห์แยกผล ไม่ส่งคำสั่งซื้อขาย",
                style=style,
                allowed_strategies=allowed,
                timeframe_map=next(m for m in config.maps if m.style == style),
                config_id=config_id,
            )
        )
        for name, title, style, allowed in choices
    )


def structural_plan(
    *,
    context: StrategyMarketContext,
    candidate_id: str,
    direction: Literal["LONG", "SHORT"],
    entry_lower: Decimal,
    entry_upper: Decimal,
    entry_id: str,
    stop_anchor: Decimal,
    stop_id: str,
    atr: Decimal,
    score: int,
    evidence: tuple[Evidence, ...],
    expires_at: dt.datetime,
    config: StrategyConfig,
    entry_type: str = "RETEST_ZONE",
    news_strategy: bool = False,
) -> TradePlanSuggestion | None:
    tick = context.tick_size
    if tick is None or tick <= 0 or not entry_id or not stop_id or atr <= 0:
        return None
    if not all(v.is_finite() and v > 0 for v in (tick, entry_lower, entry_upper, stop_anchor, atr)):
        return None

    def floor(v: Decimal) -> Decimal:
        return (v / tick).to_integral_value(rounding=ROUND_FLOOR) * tick

    def ceil(v: Decimal) -> Decimal:
        return (v / tick).to_integral_value(rounding=ROUND_CEILING) * tick

    lower, upper = floor(entry_lower), ceil(entry_upper)
    long = direction == "LONG"
    stop = (
        floor(stop_anchor - atr * config.stop_atr_buffer) if long else ceil(stop_anchor + atr * config.stop_atr_buffer)
    )
    if lower > upper or stop <= 0 or not (stop < lower if long else stop > upper):
        return None
    worst_entry = upper if long else lower
    risk = abs(worst_entry - stop)
    if risk <= 0:
        return None
    # Only presently known confirmed structural targets. No forced RR, provisional sessions or invented prices.
    target_levels = [
        level
        for level in context.key_levels
        if level.status == "CONFIRMED"
        and level.confirmed_at is not None
        and level.confirmed_at <= context.as_of
        and level.source_ids
        and (level.price > upper if long else level.price < lower)
        and level.id not in (entry_id, stop_id)
    ]
    target_levels.sort(key=lambda v: (abs(v.price - worst_entry), v.id))
    targets: list[Target] = []
    seen: set[Decimal] = set()
    for level in target_levels:
        price = floor(level.price) if long else ceil(level.price)
        if price in seen or not (price > upper if long else price < lower):
            continue
        seen.add(price)
        rr = abs(price - worst_entry) / risk
        # The nearest obstruction below minimum RR is a rejection, never silently skipped.
        if not targets and rr < config.minimum_rr:
            return None
        targets.append(
            Target(
                name=f"TP{len(targets) + 1}" if len(targets) < 2 else "RUNNER",
                price=price,
                source_id=level.id,
                rr=rr.quantize(D(".0001")),
            )
        )
        if len(targets) == 3:
            break
    if len(targets) < 2:
        return None
    return TradePlanSuggestion.model_validate(
        dict(
            id=fingerprint([candidate_id, lower, upper, stop, [t.model_dump(mode="json") for t in targets]]),
            candidate_id=candidate_id,
            symbol=context.symbol,
            direction=direction,
            entry_type=entry_type,
            entry_lower=lower,
            entry_upper=upper,
            entry_source_id=entry_id,
            stop_loss=stop,
            stop_source_id=stop_id,
            invalidation_th="ราคาปิดผ่านจุดหยุดเชิงโครงสร้าง หรือหลักฐานต้นทางถูกยืนยันว่าใช้ไม่ได้",
            targets=tuple(targets),
            score=score,
            evidence=evidence,
            warnings_th=("ข้อเสนอเพื่อวิเคราะห์เท่านั้น ไม่มีขนาดสถานะและไม่มีคำสั่งซื้อขาย",),
            news_state=context.news.trade_policy_state if news_strategy else "NOT_APPLICABLE",
            as_of=context.as_of,
            context_id=context.dependency_id("STRAT05" if news_strategy else "STRAT01"),
            expires_at=expires_at,
        )
    )


def _side(
    context: StrategyMarketContext,
    profile: TraderProfile,
    strategy: StrategyDefinition,
    config: StrategyConfig,
    direction: Literal["LONG", "SHORT"],
) -> SetupCandidate:
    mapping = profile.timeframe_map
    dependency_id = context.dependency_id(strategy.id)
    identity = fingerprint(
        [profile.model_dump(mode="json"), strategy.model_dump(mode="json"), dependency_id, direction]
    )
    expiry = context.as_of + dt.timedelta(seconds=SECONDS[mapping.trigger] * config.expiry_trigger_bars)
    evidence: list[Evidence] = []
    missing: list[str] = []
    conflicts: list[str] = []
    frames = [context.frame(tf) for tf in (mapping.context, mapping.bias, mapping.setup, mapping.trigger)]
    blocked = any(f is None or f.bars < mapping.minimum_bars for f in frames)
    if blocked:
        missing.append("ประวัติกรอบเวลาที่จำเป็นยังไม่ครบขั้นต่ำ (INSUFFICIENT_CONTEXT)")
    if any(
        f is not None and (f.as_of is None or context.as_of - f.as_of > dt.timedelta(seconds=SECONDS[f.timeframe] * 2))
        for f in frames
    ):
        blocked = True
        conflicts.append("ข้อมูลโครงสร้างบางกรอบเวลาล้าสมัย")
    news_strategy = "NEWS" in strategy.required_context
    news = context.news if news_strategy else None
    policy_key = {
        "STRAT05": "NEWS_MOMENTUM",
        "STRAT06": "NEWS_REVERSAL",
    }.get(strategy.id)
    eligibility = news.strategy_eligibility.get(policy_key, "WAITING") if policy_key and news else "ALLOWED"
    if news is not None:
        if (
            news.calendar_state != "AVAILABLE"
            or (context.mode == "ACTUAL" and news.source_mode != "LIVE")
            or context.as_of - news.as_of > dt.timedelta(minutes=1)
        ):
            blocked = True
            conflicts.append("ข่าวจริงยังไม่พร้อม: ข่าวทดสอบหรือข้อมูลที่ไม่ครบใช้ยืนยัน Setup ข่าวไม่ได้")
        if news.data_quality in ("CONFLICT", "PARTIAL", "UNAVAILABLE") or news.release_status != "RELEASED":
            blocked = True
            conflicts.append(news.release_status if news.release_status != "RELEASED" else "INCOMPLETE_RELEASE_GROUP")
        if eligibility in ("BLOCKED", "WAITING") or news.trade_policy_state == "RESTRICTED":
            blocked = True
            conflicts.append("บริบทข่าวยังไม่อนุญาตกลยุทธ์ข่าวนี้")
    safety = news if news is not None else context.market_safety
    if safety.spread_state in ("SPREAD_EXTREME", "SPREAD_ELEVATED", "UNAVAILABLE"):
        blocked = True
        conflicts.append(
            "ยังไม่มีข้อมูลส่วนต่างราคาที่ตรวจสอบได้" if safety.spread_state == "UNAVAILABLE" else "ส่วนต่างราคาไม่เหมาะสม"
        )
    if safety.volatility_state in ("EXTREME", "UNAVAILABLE"):
        blocked = True
        conflicts.append(
            "ยังไม่มีข้อมูลความผันผวนที่ตรวจสอบได้" if safety.volatility_state == "UNAVAILABLE" else "ความผันผวนสูงเกินเงื่อนไข"
        )
    if news is not None and news.macro_bias == "CONFLICTING":
        blocked = True
        conflicts.append("องค์ประกอบข่าวขัดแย้งกัน")
    if news is not None and not blocked:
        evidence.append(
            Evidence(
                code="NEWS",
                description_th="บริบทข่าวผ่านเงื่อนไขบังคับ",
                source_ids=(news.fingerprint,),
                confirmed_at=news.as_of,
                weight=10,
            )
        )
    entry: tuple[Decimal, Decimal, str, Decimal, str] | None = None
    atr = D(0)
    long = direction == "LONG"
    expected = "BULLISH" if long else "BEARISH"
    if all(f is not None and f.bars for f in frames):
        htf, bias, setup, trigger = (f for f in frames if f is not None)
        hs, bs, ss, ts = htf.analysis, bias.analysis, setup.analysis, trigger.analysis
        bars = trigger.candles
        latest = bars[-1]
        atr_item = ss.indicators.get("ATR")
        atr = atr_item.value if atr_item and atr_item.value is not None else D(0)
        earliest = context.as_of - dt.timedelta(seconds=SECONDS[mapping.trigger] * config.event_lookback_bars)
        events = [
            event
            for event in ts.events
            if earliest <= event.confirmed_at <= context.as_of and event.direction == expected
        ]
        event: StructureEvent | None = events[-1] if events else None
        aligned = hs.external_state == expected and bs.external_state == expected
        opposite = "BEARISH" if long else "BULLISH"
        if hs.external_state == opposite or bs.external_state == opposite:
            conflicts.append("โครงสร้างกรอบใหญ่ขัดแย้งกับทิศทางที่พิจารณา")
            blocked = True
        if aligned:
            evidence.append(
                Evidence(
                    code="HTF",
                    description_th="โครงสร้างกรอบใหญ่สอดคล้องกัน",
                    source_ids=(htf.input_id, bias.input_id),
                    weight=15,
                )
            )
        elif strategy.id in ("STRAT01", "STRAT02", "STRAT03", "STRAT05", "STRAT06"):
            missing.append("รอความสอดคล้องของโครงสร้างกรอบใหญ่")
        if event:
            expiry = event.confirmed_at + dt.timedelta(seconds=SECONDS[mapping.trigger] * config.expiry_trigger_bars)
            if context.as_of >= expiry:
                missing.append("หลักฐานโครงสร้างเกินอายุตามจำนวนแท่งที่กำหนด")
            evidence.append(
                Evidence(
                    code="STRUCTURE",
                    description_th="พบโครงสร้างยืนยันกรอบเล็ก",
                    source_ids=(event.id,),
                    confirmed_at=event.confirmed_at,
                    weight=25,
                )
            )
        else:
            missing.append("ยังไม่มีโครงสร้างยืนยันกรอบเล็ก")
        sweep = next(
            (
                level
                for level in reversed(ss.liquidity)
                if level.status == "SWEPT"
                and level.side == ("LOW" if long else "HIGH")
                and level.swept_at is not None
                and earliest <= level.swept_at <= context.as_of
            ),
            None,
        )
        reclaimed = bool(
            sweep
            and event
            and sweep.swept_at
            and event.confirmed_at >= sweep.swept_at
            and any(
                c.open_time >= sweep.swept_at
                and c.open_time + dt.timedelta(seconds=SECONDS[mapping.trigger]) <= event.confirmed_at
                and (c.close > sweep.price if long else c.close < sweep.price)
                for c in bars
            )
        )
        reversal = event is not None and event.kind in ("CHOCH", "MSS")
        if sweep and reclaimed:
            evidence.append(
                Evidence(
                    code="LIQUIDITY",
                    description_th="กวาดสภาพคล่องและราคาปิดกลับเข้าระดับเดิม",
                    source_ids=(sweep.id,),
                    confirmed_at=sweep.swept_at,
                    weight=20,
                )
            )
        if strategy.id in ("STRAT01", "STRAT06") and not (sweep and reclaimed and reversal):
            missing.append("รอกวาดสภาพคล่อง กลับเข้าระดับ และ CHOCH/MSS ตามลำดับ")
        zones = [
            z
            for z in ss.zones
            if z.kind in ("FVG", "OB")
            and z.direction == expected
            and z.status in ("OPEN", "PARTIALLY_FILLED", "ACTIVE", "MITIGATED")
            and z.confirmed_at <= latest.open_time
            and (
                strategy.id not in ("STRAT01", "STRAT06") or event is not None and z.confirmed_at >= event.confirmed_at
            )
        ]
        zone = next(
            (
                z
                for z in reversed(zones)
                if latest.low <= z.upper_bound
                and latest.high >= z.lower_bound
                and (latest.close > z.upper_bound if long else latest.close < z.lower_bound)
            ),
            None,
        )
        if strategy.id in ("STRAT01", "STRAT02", "STRAT05", "STRAT06"):
            if zone:
                anchor = (
                    min(zone.lower_bound, sweep.sweep_price or sweep.price)
                    if long and sweep
                    else (
                        max(zone.upper_bound, sweep.sweep_price or sweep.price)
                        if sweep
                        else zone.lower_bound
                        if long
                        else zone.upper_bound
                    )
                )
                entry = (zone.lower_bound, zone.upper_bound, zone.id, anchor, sweep.id if sweep else zone.id)
                evidence.append(
                    Evidence(
                        code="KEY_LEVEL",
                        description_th="ราคาทดสอบและปฏิเสธโซนเชิงโครงสร้าง",
                        source_ids=(zone.id,),
                        confirmed_at=zone.confirmed_at,
                        weight=10,
                    )
                )
            else:
                missing.append("รอการกลับทดสอบและปฏิเสธ FVG/OB ที่ยังใช้ได้")
        if strategy.id == "STRAT02":
            if not any(e.kind == "BOS" and e.direction == expected for e in ss.events):
                missing.append("ยังไม่มี BOS ยืนยันแนวโน้ม")
            if ss.regime not in ("TRENDING_UP", "TRENDING_DOWN", "PULLBACK"):
                missing.append("สภาวะราคาไม่ใช่แนวโน้มหรือการย่อ")
        if strategy.id == "STRAT03":
            pattern = next(
                (
                    p
                    for p in reversed(setup.patterns)
                    if p.status == "CONFIRMED"
                    and p.direction == direction
                    and p.confirmed_at
                    and p.confirmed_at <= latest.open_time < p.expires_at
                ),
                None,
            )
            if (
                pattern
                and pattern.confirmed_at
                and event
                and event.displacement
                and event.confirmed_at >= pattern.confirmed_at
            ):
                neck = pattern.neckline
                tol = atr * config.tolerance_atr
                if (
                    latest.low <= neck + tol
                    and latest.high >= neck - tol
                    and (latest.close > neck + tol if long else latest.close < neck - tol)
                ):
                    entry = (neck - tol, neck + tol, pattern.id, pattern.lower if long else pattern.upper, pattern.id)
                    evidence.append(
                        Evidence(
                            code="PATTERN",
                            description_th="รูปแบบยืนยันและกลับทดสอบหลังทะลุด้วยแรง",
                            source_ids=(pattern.id, event.id),
                            confirmed_at=pattern.confirmed_at,
                            weight=10,
                        )
                    )
            if entry is None:
                missing.append("รอรูปแบบยืนยัน ราคาปิดทะลุด้วยแรง และกลับทดสอบหลังยืนยัน")
        if strategy.id == "STRAT04":
            dr = ss.dealing_range
            adx = ss.indicators.get("ADX")
            ranging = ss.regime == "RANGING" and adx is not None and adx.value is not None and adx.value < 25
            if not ranging or dr is None:
                missing.append("ต้องมีกรอบราคายืนยันและ ADX ต่ำกว่าเกณฑ์แนวโน้ม")
            elif event and reversal:
                bound = dr.lower_bound if long else dr.upper_bound
                tol = atr * config.tolerance_atr
                if (
                    latest.low <= bound + tol
                    and latest.high >= bound - tol
                    and (latest.close > bound + tol if long else latest.close < bound - tol)
                ):
                    entry = (bound - tol, bound + tol, dr.swing_ids[0], bound, dr.swing_ids[0])
                    evidence.append(
                        Evidence(
                            code="KEY_LEVEL",
                            description_th="ปฏิเสธขอบกรอบที่ยืนยันในสภาวะ Sideway",
                            source_ids=tuple(dr.swing_ids),
                            confirmed_at=dr.confirmed_at,
                            weight=10,
                        )
                    )
            if entry is None:
                missing.append("รอปฏิเสธขอบกรอบและเปลี่ยนโครงสร้าง")
        if news is not None:
            released = [
                e
                for e in news.events
                if e.id in (news.active_group.event_ids if news.active_group else [])
                and (e.actual is not None or e.unit == "NON_NUMERIC")
                and e.released_at is not None
                and e.released_at <= context.as_of
                and e.available_at <= context.as_of
            ]
            numeric_release = any(e.unit != "NON_NUMERIC" for e in released)
            expected_macro = "NEGATIVE" if long else "POSITIVE"
            reaction_ok = news.reaction_state in (
                ("STRONG_DIRECTIONAL", "BREAKOUT") if strategy.id == "STRAT05" else ("LIQUIDITY_SWEEP_REVERSAL",)
            )
            if (
                not released
                or numeric_release
                and expected_macro not in news.macro_bias
                or not reaction_ok
                or news.spread_state != "SPREAD_NORMAL"
                or news.volatility_state not in ("NORMAL", "ELEVATED")
                or news.structure_confirmation.status != "ALIGNED"
                or eligibility != "ELIGIBLE"
            ):
                missing.append("รอผลข่าวจริง ทิศทางข่าว/ราคา โครงสร้าง และส่วนต่างราคาที่ตรวจสอบได้")
            if strategy.id == "STRAT06" and not any(e.impact == "HIGH" for e in released):
                missing.append("ยังไม่มีข่าวผลกระทบสูงที่ประกาศแล้ว")
            if released and event and event.confirmed_at < max(e.released_at for e in released if e.released_at):
                missing.append("การยืนยันโครงสร้างต้องเกิดหลังประกาศข่าว")
        # Indicators contribute modest supporting evidence only; never replace structural requirements.
        rsi = ts.indicators.get("RSI")
        if rsi and rsi.value is not None and (rsi.value >= 50 if long else rsi.value <= 50):
            evidence.append(
                Evidence(
                    code="INDICATOR",
                    description_th="RSI สนับสนุนทิศทาง เป็นหลักฐานประกอบเท่านั้น",
                    source_ids=(trigger.input_id,),
                    weight=5,
                )
            )
    score = max(0, min(100, sum(e.weight for e in evidence) - 15 * len(conflicts)))
    plan = None
    if entry is not None and not missing and not blocked:
        plan = structural_plan(
            context=context,
            candidate_id=identity,
            direction=direction,
            entry_lower=entry[0],
            entry_upper=entry[1],
            entry_id=entry[2],
            stop_anchor=entry[3],
            stop_id=entry[4],
            atr=atr,
            score=min(100, score + 5),
            evidence=tuple(evidence),
            expires_at=expiry,
            config=config,
            news_strategy=news_strategy,
            entry_type="BREAKOUT_RETEST" if strategy.id == "STRAT03" else "RETEST_ZONE",
        )
        if plan:
            evidence.append(
                Evidence(
                    code="GEOMETRY",
                    description_th="SL/TP มาจากโครงสร้างและผ่าน RR ขั้นต่ำ",
                    source_ids=tuple(t.source_id for t in plan.targets),
                    weight=5,
                )
            )
            score = min(100, score + 5)
        else:
            missing.append("เรขาคณิตราคาไม่ผ่าน: ต้องมี tick size, SL และเป้าหมายจริงอย่างน้อยสองระดับพร้อม RR")
    state = "BLOCKED_CONTEXT" if blocked else "READY" if plan else "WAITING_CONFIRMATION" if entry else "NO_TRADE"
    return SetupCandidate.model_validate(
        dict(
            id=identity,
            profile_id=profile.id,
            strategy_id=strategy.id,
            symbol=context.symbol,
            direction=direction if entry else "NO_TRADE",
            status=state,
            score=score,
            detected_at=context.as_of,
            confirmed_at=context.as_of if plan else None,
            expires_at=expiry,
            context_id=dependency_id,
            upstream_ids=tuple(f.input_id for f in context.frames)
            + ((news.fingerprint,) if news else context.market_safety.source_ids),
            news_provenance=NewsCandidateProvenance(
                context_fingerprint=news.fingerprint,
                source=news.source,
                as_of=news.as_of,
                news_engine_version=news.news_engine_version,
                event_vintages=tuple(
                    e
                    for e in news.events
                    if e.id in (news.active_group.event_ids if news.active_group else []) or e in news.upcoming_events
                ),
                phase3_input_ids=tuple(f.input_id for f in context.frames),
            )
            if news
            else None,
            evidence=tuple(evidence),
            missing_conditions=tuple(dict.fromkeys(missing)),
            conflicts=tuple(dict.fromkeys(conflicts)),
            invalidation_th="ใช้การยืนยันจากข้อมูลต้นทาง จุดหยุดเชิงโครงสร้าง และเวลาหมดอายุ; การหายจาก snapshot ไม่ใช่การยกเลิก",
            plan=plan,
        )
    )


class Playbook:
    """No provider/session dependency is available to a playbook."""

    def __init__(self, definition: StrategyDefinition):
        self.definition = definition

    def evaluate(
        self, context: StrategyMarketContext, profile: TraderProfile, config: StrategyConfig
    ) -> SetupCandidate:
        results = [
            _side(context, profile, self.definition, config, cast(Literal["LONG", "SHORT"], side))
            for side in ("LONG", "SHORT")
        ]
        ready = [r for r in results if r.status == "READY"]
        chosen = sorted(
            results, key=lambda r: (r.status == "READY", r.direction != "NO_TRADE", r.score, r.id), reverse=True
        )[0]
        if len(ready) == 2:
            return chosen.model_copy(
                update={
                    "direction": "NO_TRADE",
                    "status": "NO_TRADE",
                    "plan": None,
                    "conflicts": chosen.conflicts + ("กลยุทธ์พบเงื่อนไขสองทิศทางพร้อมกัน",),
                }
            )
        return chosen


REGISTRY = {definition.id: Playbook(definition) for definition in DEFINITIONS}


class EvaluationCache:
    """Bounded per-strategy cache; calendar-only revisions reuse market playbooks."""

    def __init__(self, limit: int = 256):
        self.limit = limit
        self.values: OrderedDict[str, SetupCandidate] = OrderedDict()

    def candidate(
        self, context: StrategyMarketContext, trader: TraderProfile, config: StrategyConfig, strategy_id: str
    ) -> SetupCandidate:
        key = fingerprint([context.dependency_id(strategy_id), trader, config, strategy_id])
        if key not in self.values:
            self.values[key] = REGISTRY[strategy_id].evaluate(context, trader, config)
        self.values.move_to_end(key)
        result = self.values[key]
        if len(self.values) > self.limit:
            self.values.popitem(last=False)
        return result


def evaluate(
    context: StrategyMarketContext,
    config: StrategyConfig,
    traders: tuple[TraderProfile, ...] | None = None,
    cache: EvaluationCache | None = None,
) -> Evaluation:
    if config != StrategyConfig.model_validate_json(context.strategy_config_json):
        raise ValueError("Strategy configuration/context mismatch")
    traders = traders if traders is not None else profiles(config, context.config_id)
    if len({p.id for p in traders}) != len(traders):
        raise ValueError("Profile identifiers must be unique")
    candidates: list[SetupCandidate] = []
    for trader in traders:
        if trader.config_id != context.config_id or trader.timeframe_map not in config.maps:
            raise ValueError("Profile/context configuration mismatch")
        if trader.enabled:
            for strategy_id in trader.allowed_strategies:
                if strategy_id not in REGISTRY:
                    raise ValueError("Unknown strategy")
                candidates.append(
                    cache.candidate(context, trader, config, strategy_id)
                    if cache
                    else REGISTRY[strategy_id].evaluate(context, trader, config)
                )
    candidates.sort(key=lambda c: (-c.score, c.profile_id, c.strategy_id, c.id))
    from app.services.strategy.identity import components, request_id

    refs = components(context, traders, DEFINITIONS, tuple(candidates))
    return Evaluation(
        id=request_id(context, traders, refs),
        identity_version=EVALUATION_VERSION,
        scope="REQUEST",
        component_ids=refs,
        context=context,
        profiles=traders,
        strategies=DEFINITIONS,
        candidates=tuple(candidates),
    )
