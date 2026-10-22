"""Temporary independent D2C seam probe. Delete after the verification run."""

from __future__ import annotations

import ast
import datetime as dt
import traceback
from pathlib import Path

from pydantic import ValidationError

from app.services.backtesting import risk_replay as integration
from app.services.backtesting.replay import replay
from app.services.backtesting.replay_domain import ReplayStrategyEvent
from app.services.backtesting.risk_replay import replay_risk
from app.services.backtesting.risk_replay_domain import (
    RiskEvaluationStatus,
    RiskReplayError,
    RiskReplayFailureCode,
)
from app.services.market_data.domain import Timeframe
from app.services.strategy.domain import Evidence, Target, TradePlanSuggestion
from app.services.strategy.engine import REGISTRY
from tests.test_backtesting_d2c import (
    D,
    START,
    archived_inputs,
    config,
    fresh_quotes,
    inputs,
    quote,
    scheduled_news,
)

RAW_TYPES = (TypeError, ValidationError, AttributeError)
PACKAGE = Path(__file__).resolve().parent / "app" / "services" / "backtesting"
D2C_FILES = ("risk_replay.py", "risk_replay_domain.py", "risk_replay_fingerprint.py")
FORBIDDEN_IMPORT_PREFIXES = (
    "app.services.risk.engine",
    "app.services.risk.live_adapter",
    "app.services.risk.repository",
    "app.services.risk.kill_switch",
    "app.services.ai",
    "sqlalchemy",
    "MetaTrader5",
    "app.models",
    "app.api",
)
FORBIDDEN_CALLS = {"order_send", "Session", "AsyncSession", "commit", "execute", "now", "utcnow", "activate"}
results: list[tuple[str, str]] = []


def record(name: str, detail: str, ok: bool) -> None:
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def call_forged(forged, stop_at):
    original = integration.replay

    def fake(*_args, **_kwargs):
        return forged

    integration.replay = fake
    try:
        return replay_risk(inputs(), config(), stop_at=stop_at)
    finally:
        integration.replay = original


def classify(operation):
    try:
        return ("ok", operation())
    except RiskReplayError as error:
        banned = [t.__name__ for t in RAW_TYPES if isinstance(error, t)]
        cause = type(error.__cause__).__name__ if error.__cause__ else None
        return ("stable", error, banned, cause)
    except Exception as error:
        return ("raw", error)


def expect_causality(name: str, operation) -> None:
    kind, *rest = classify(operation)
    if kind == "stable":
        error, banned, cause = rest
        ok = (
            type(error) is RiskReplayError
            and not banned
            and error.code is RiskReplayFailureCode.CAUSALITY_VIOLATION
            and str(error) == RiskReplayFailureCode.CAUSALITY_VIOLATION.value
        )
        record(name, f"code={error.code.value} type={type(error).__name__} cause={cause} banned={banned}", ok)
        return
    if kind == "raw":
        error = rest[0]
        record(name, f"RAW {type(error).__name__}: {error}", False)
        return
    record(name, f"unexpected success {type(rest[0]).__name__}", False)


def forge(perturb: str, source):
    if perturb == "reversed":
        return source.model_copy(update={"events": source.events[::-1]})
    if perturb == "duplicate":
        return source.model_copy(update={"events": (source.events[0],) + source.events})
    if perturb == "beyond_cutoff":
        late = source.events[-1].model_copy(update={"as_of": source.cutoff + dt.timedelta(minutes=1)})
        return source.model_copy(update={"events": source.events[:-1] + (late,)})
    if perturb == "naive_event_as_of":
        naive = source.events[-1].model_copy(update={"as_of": source.events[-1].as_of.replace(tzinfo=None)})
        return source.model_copy(update={"events": source.events[:-1] + (naive,)})
    if perturb == "naive_event_as_of_first":
        naive = source.events[0].model_copy(update={"as_of": source.events[0].as_of.replace(tzinfo=None)})
        return source.model_copy(update={"events": (naive,) + source.events[1:]})
    if perturb == "naive_cutoff":
        return source.model_copy(update={"cutoff": source.cutoff.replace(tzinfo=None)})
    if perturb == "both_naive":
        events = tuple(e.model_copy(update={"as_of": e.as_of.replace(tzinfo=None)}) for e in source.events)
        return source.model_copy(update={"events": events, "cutoff": source.cutoff.replace(tzinfo=None)})
    if perturb == "non_event_none":
        return source.model_copy(update={"events": (None,) + source.events})
    if perturb == "non_event_object":
        return source.model_copy(update={"events": (object(),) + source.events})
    if perturb == "non_event_str":
        return source.model_copy(update={"events": ("not-an-event",) + source.events})
    if perturb == "partial_duck":
        template = source.events[0]

        class _Partial:
            as_of = template.as_of
            profile_id = template.profile_id
            strategy_id = template.strategy_id
            candidate_id = "forged-partial"

        return source.model_copy(update={"events": (_Partial(),)})
    if perturb == "quacking_no_plan":
        template = source.events[0]

        class _Quack:
            as_of = template.as_of
            profile_id = template.profile_id
            strategy_id = template.strategy_id
            candidate_id = "forged-quack"
            event_fingerprint = template.event_fingerprint
            trade_plan = None

        return source.model_copy(update={"events": (_Quack(),)})
    if perturb == "trade_plan_object":
        broken = source.events[-1].model_copy(update={"trade_plan": object()})
        return source.model_copy(update={"events": source.events[:-1] + (broken,)})
    if perturb == "utcoffset_none":
        class _NullOffset(dt.tzinfo):
            def utcoffset(self, _value):
                return None

            def dst(self, _value):
                return None

            def tzname(self, _value):
                return "NULL"

        stamped = source.events[-1].as_of.replace(tzinfo=_NullOffset())
        naive = source.events[-1].model_copy(update={"as_of": stamped})
        return source.model_copy(update={"events": source.events[:-1] + (naive,)})
    raise AssertionError(perturb)


def install_plan():
    original = REGISTRY["STRAT01"].evaluate

    def evaluate(context, profile, strategy_config):
        candidate = original(context, profile, strategy_config)
        plan = TradePlanSuggestion(
            id="fixture_plan_" + candidate.id,
            candidate_id=candidate.id,
            symbol="XAUUSD",
            direction="LONG",
            entry_type="LIMIT_ZONE",
            entry_lower=D("2000"),
            entry_upper=D("2002"),
            entry_source_id="test_entry",
            stop_loss=D("1995"),
            stop_source_id="test_stop",
            invalidation_th="test-only structural invalidation",
            targets=(
                Target(name="TP1", price=D("2010"), source_id="test_target_1", rr=D("1.1")),
                Target(name="TP2", price=D("2020"), source_id="test_target_2", rr=D("2.5")),
            ),
            score=85,
            evidence=(Evidence(code="TEST", description_th="explicit test-only suggestion"),),
            warnings_th=(),
            news_state="CALM",
            status="SUGGESTION_ONLY",
            as_of=context.as_of,
            context_id=candidate.context_id,
            expires_at=context.as_of + dt.timedelta(hours=1),
        )
        return candidate.model_copy(
            update={"direction": "LONG", "status": "READY", "confirmed_at": context.as_of, "plan": plan}
        )

    REGISTRY["STRAT01"].evaluate = evaluate
    return original


def probe_stream() -> None:
    source_inputs = inputs()
    source = replay(source_inputs, stop_at=START + dt.timedelta(minutes=10))
    assert len(source.events) >= 2, len(source.events)
    assert all(isinstance(event, ReplayStrategyEvent) for event in source.events)
    cases = [
        "reversed",
        "duplicate",
        "beyond_cutoff",
        "naive_event_as_of",
        "naive_event_as_of_first",
        "naive_cutoff",
        "both_naive",
        "non_event_none",
        "non_event_object",
        "non_event_str",
        "partial_duck",
        "quacking_no_plan",
        "trade_plan_object",
        "utcoffset_none",
    ]
    for name in cases:
        forged = forge(name, source)
        expect_causality(name, lambda forged=forged, stop=source.cutoff: call_forged(forged, stop))


def probe_behavior() -> None:
    calls = {"n": 0}
    original_eval = integration.evaluate_pure_risk

    def counting(value):
        calls["n"] += 1
        return original_eval(value)

    integration.evaluate_pure_risk = counting
    try:
        result = replay_risk(inputs(), config(), stop_at=START + dt.timedelta(minutes=10))
    except Exception as error:
        record("no_plan_sanity", f"RAW {type(error).__name__}: {error}", False)
    else:
        ok = (
            calls["n"] == 0
            and result.risk_events_evaluated == 0
            and result.no_plan_events == result.strategy_events_seen == len(result.events) >= 2
            and all(e.risk_evaluation_status is RiskEvaluationStatus.NOT_EVALUATED_NO_PLAN for e in result.events)
            and all(e.pure_risk_result is None and e.plan_id is None for e in result.events)
        )
        record(
            "no_plan_sanity",
            f"events={len(result.events)} evaluated={result.risk_events_evaluated} pure_calls={calls['n']}",
            ok,
        )
    finally:
        integration.evaluate_pure_risk = original_eval

    kind, *rest = classify(
        lambda: replay_risk(
            inputs(),
            config().model_copy(update={"policy": config().policy.model_copy(update={"version": "wrong"})}),
        )
    )
    if kind == "stable":
        error, banned, cause = rest
        ok = (
            not banned
            and error.code is RiskReplayFailureCode.CONFIGURATION_INVALID
            and str(error) == "RISK_REPLAY_CONFIGURATION_INVALID"
        )
        record("policy_version_mismatch", f"code={error.code.value} cause={cause}", ok)
    else:
        record("policy_version_mismatch", f"{kind} {rest}", False)

    original_plan = install_plan()
    try:
        baseline = replay_risk(inputs(quotes=fresh_quotes()), config(), stop_at=START)
        future_only = replay_risk(
            inputs(quotes=(quote(START + dt.timedelta(seconds=1), ask="2009"),)), config(), stop_at=START
        )
        earlier = quote(START - dt.timedelta(seconds=2))
        observed_future = quote(START - dt.timedelta(seconds=1), observed=START + dt.timedelta(seconds=1), ask="2009")
        timestamp_future = quote(START + dt.timedelta(seconds=1), ask="2009")
        mixed = replay_risk(
            inputs(quotes=(earlier, observed_future, timestamp_future)), config(), stop_at=START
        )
        quote_ok = (
            future_only.events[0].pure_risk_result.decision == "BLOCKED"
            and future_only.events[0].quote_timestamp is None
            and mixed.events[0].quote_timestamp == earlier.timestamp
            and mixed.events[0].quote_observed_at == earlier.observed_at
            and mixed.events[0].pure_risk_result.decision == "APPROVED"
        )
        record(
            "future_quote",
            f"future_only={future_only.events[0].pure_risk_result.decision} "
            f"mixed_ts={mixed.events[0].quote_timestamp} decision={mixed.events[0].pure_risk_result.decision}",
            quote_ok,
        )

        original_news = scheduled_news()
        future_news = scheduled_news(available=START + dt.timedelta(minutes=30), version=2, impact="LOW")
        prefix_cutoff = START + dt.timedelta(minutes=5)
        first = replay_risk(archived_inputs((original_news,)), config(news=True), stop_at=prefix_cutoff)
        second = replay_risk(
            archived_inputs((original_news, future_news)), config(news=True), stop_at=prefix_cutoff
        )
        news_ok = first.events == second.events and first.risk_replay_fingerprint == second.risk_replay_fingerprint
        record(
            "future_news",
            f"equal_events={first.events == second.events} equal_output={news_ok} "
            f"input_changed={first.risk_replay_input_fingerprint != second.risk_replay_input_fingerprint}",
            news_ok and first.risk_replay_input_fingerprint != second.risk_replay_input_fingerprint,
        )

        source = inputs(quotes=fresh_quotes())
        configuration = config()
        expected = replay_risk(source, configuration, stop_at=START + dt.timedelta(minutes=5))
        original_replay = integration.replay

        def mutate(private, **kwargs):
            object.__setattr__(source.candles[Timeframe.M1][0], "volume", D("999"))
            object.__setattr__(configuration.policy, "max_risk_per_trade_pct", D("5"))
            return original_replay(private, **kwargs)

        integration.replay = mutate
        try:
            mutated = replay_risk(source, configuration, stop_at=expected.cutoff)
        finally:
            integration.replay = original_replay
        mutation_ok = mutated == expected
        kind, *rest = classify(lambda: replay_risk(source, config(), stop_at=START))
        follow_ok = kind == "stable" and rest[0].code is RiskReplayFailureCode.INPUT_INVALID and not rest[1]
        record(
            "caller_mutation",
            f"private_snapshot_stable={mutation_ok} followup={kind} "
            f"code={getattr(rest[0], 'code', None)}",
            mutation_ok and follow_ok,
        )
        _ = baseline
    except Exception as error:
        record("behavior_exception", f"RAW {type(error).__name__}: {error}\n{traceback.format_exc()}", False)
    finally:
        REGISTRY["STRAT01"].evaluate = original_plan


def probe_isolation() -> None:
    violations = []
    for name in D2C_FILES:
        path = PACKAGE / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module in imported:
                if module.startswith(FORBIDDEN_IMPORT_PREFIXES) or module in {"sqlalchemy", "MetaTrader5"}:
                    violations.append((name, "import", module))
            if isinstance(node, ast.Call):
                call = getattr(node.func, "id", getattr(node.func, "attr", None))
                if call in FORBIDDEN_CALLS:
                    violations.append((name, "call", call))
            if isinstance(node, (ast.AsyncFunctionDef, ast.Await)):
                violations.append((name, "async", type(node).__name__))
        text = path.read_text(encoding="utf-8")
        for token in ("order_send", "KillSwitchManager", "RiskEngine", "AsyncSession", "live_adapter"):
            if token in text:
                violations.append((name, "text", token))
    record("isolation", f"violations={violations}", violations == [])


def main() -> int:
    probe_stream()
    probe_behavior()
    probe_isolation()
    failed = [row for row in results if row[1] == "FAIL"]
    print(f"SUMMARY pass={len(results) - len(failed)} fail={len(failed)} total={len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
