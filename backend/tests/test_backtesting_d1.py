"""Batch D1 pure contract, resource, coverage, and fingerprint acceptance."""

import datetime as dt
import hashlib
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.backtesting.domain import (
    BACKTEST_CONTRACT_VERSION,
    BACKTEST_FINGERPRINT_VERSION,
    REPLAY_ENGINE_VERSION_PLACEHOLDER,
    BacktestProvenance,
    BacktestRunConfig,
    BacktestRunEnvelope,
    BacktestRunManifest,
    CostAssumptions,
    CoverageGap,
    CoverageGapCode,
    CoverageStatus,
    DataCoverage,
    GapExpectation,
    NewsVintageCoverage,
    RunFailureCode,
    RunLifecycle,
    TimeframeCoverage,
    is_backtest_identity,
)
from app.services.backtesting.fingerprint import (
    canonical_json,
    config_fingerprint,
    coverage_fingerprint,
    data_provenance_fingerprint,
    resource_policy_fingerprint,
    run_input_fingerprint,
    semantic_fingerprint,
)
from app.services.backtesting.policy import (
    MAX_ACTIVE_RUNS_PER_USER,
    MAX_ACTIVE_RUNS_SYSTEM,
    MAX_API_PAGE_SIZE,
    MAX_CANDIDATES_PER_RUN,
    MAX_EQUITY_POINTS_PER_RUN,
    MAX_ESTIMATED_OUTPUT_BYTES,
    MAX_PENDING_RUNS,
    MAX_PRIMARY_REPLAY_EVENTS,
    MAX_REQUESTED_PERIOD_DAYS,
    MAX_TOTAL_CANDLE_INPUTS,
    MAX_TRADES_PER_RUN,
    BacktestResourcePolicy,
    ResourceRejectionCode,
    ResourceUsage,
    validate_resource_usage,
)
from app.services.market_data.domain import Timeframe

UTC = dt.UTC
START = dt.datetime(2025, 1, 1, tzinfo=UTC)
END = dt.datetime(2025, 2, 1, tzinfo=UTC)
WARMUP = dt.datetime(2024, 12, 1, tzinfo=UTC)
DATA_SHA = "a" * 64


def costs(**changes) -> CostAssumptions:
    values = {
        "spread_price": Decimal("0.30"),
        "slippage_price_per_side": Decimal("0.01"),
        "commission_usd_per_lot_per_side": Decimal("3.50"),
    }
    values.update(changes)
    return CostAssumptions(**values)


def config(**changes) -> BacktestRunConfig:
    values = {
        "symbol": "XAUUSD",
        "start": START,
        "end": END,
        "timeframe": Timeframe.M5,
        "strategy_id": "STRAT01",
        "profile_id": "research",
        "initial_balance": Decimal("10000.00"),
        "costs": costs(),
    }
    values.update(changes)
    return BacktestRunConfig(**values)


def news_coverage(*, required=False, available=False) -> NewsVintageCoverage:
    values = {"required": required, "available": available}
    if available:
        values.update(
            source="fixture_news_vintage_v1",
            vintage_start=WARMUP,
            vintage_end=END,
            availability_verified_at=END,
        )
    return NewsVintageCoverage(**values)


def coverage(**changes) -> DataCoverage:
    frame = TimeframeCoverage(
        timeframe=Timeframe.M5,
        available_start=WARMUP,
        available_end=END,
        requested_events=8_928,
        available_events=8_928,
        source="fixture_market_v1",
    )
    values = {
        "requested_start": START,
        "requested_end": END,
        "warmup_start": WARMUP,
        "usable_start": START,
        "usable_end": END,
        "symbol": "XAUUSD",
        "timeframe": Timeframe.M5,
        "source": "fixture_market_v1",
        "requested_primary_events": 8_928,
        "available_primary_events": 8_928,
        "total_candle_inputs": 44_640,
        "required_timeframes": (Timeframe.M5,),
        "timeframe_coverage": (frame,),
        "gaps": (),
        "news_vintages": news_coverage(),
        "data_fingerprint": DATA_SHA,
        "status": CoverageStatus.SUFFICIENT,
    }
    values.update(changes)
    return DataCoverage(**values)


def coverage_with_source(source: str) -> DataCoverage:
    frame = TimeframeCoverage(
        timeframe=Timeframe.M5,
        available_start=WARMUP,
        available_end=END,
        requested_events=8_928,
        available_events=8_928,
        source=source,
    )
    return coverage(source=source, timeframe_coverage=(frame,))


def coverage_with_shortfall(status: CoverageStatus = CoverageStatus.SUFFICIENT) -> DataCoverage:
    frame = TimeframeCoverage(
        timeframe=Timeframe.M5,
        available_start=WARMUP,
        available_end=END,
        requested_events=8_928,
        available_events=8_927,
        source="fixture_market_v1",
    )
    return coverage(
        available_primary_events=8_927,
        timeframe_coverage=(frame,),
        status=status,
    )


def manifest(*, cfg=None, cov=None, **provenance_changes) -> BacktestRunManifest:
    cfg = cfg or config()
    cov = cov or coverage()
    values = {
        "market_source": cov.source,
        "symbol": cfg.symbol,
        "timeframes": cov.required_timeframes,
        "requested_start": cfg.start,
        "requested_end": cfg.end,
        "usable_start": cov.usable_start,
        "usable_end": cov.usable_end,
        "strategy_id": cfg.strategy_id,
        "strategy_version": "strategy-1.2.1",
        "profile_id": cfg.profile_id,
        "risk_policy_version": "risk-policy-1.0.0",
        "costs": cfg.costs,
        "data_coverage_fingerprint": coverage_fingerprint(cov),
        "data_fingerprint": cov.data_fingerprint,
        "configuration_fingerprint": config_fingerprint(cfg),
    }
    values.update(provenance_changes)
    provenance = BacktestProvenance(**values)
    return BacktestRunManifest(
        config=cfg,
        coverage=cov,
        provenance=provenance,
        resource_policy_fingerprint=resource_policy_fingerprint(BacktestResourcePolicy()),
        contract_version=provenance.backtest_contract_version,
    )


def test_hand_calculable_fixture_and_deep_immutability():
    cfg = config()
    cov = coverage()
    item = manifest(cfg=cfg, cov=cov)
    assert cfg.symbol == "XAUUSD"
    assert cfg.timeframe is Timeframe.M5
    assert cfg.strategy_id == "STRAT01"
    assert cfg.profile_id == "research"
    assert cfg.initial_balance == Decimal("10000.00")
    assert cfg.costs.spread_price == Decimal("0.30")
    assert item.coverage.status is CoverageStatus.SUFFICIENT
    with pytest.raises(ValidationError):
        cfg.initial_balance = Decimal("1")
    with pytest.raises(ValidationError):
        cov.required_timeframes = (Timeframe.H1,)


def test_period_exact_boundary_and_equivalent_utc_normalization():
    exact = config(end=START + dt.timedelta(days=366))
    offset = dt.timezone(dt.timedelta(hours=7))
    equivalent = config(
        start=START.astimezone(offset),
        end=(START + dt.timedelta(days=366)).astimezone(offset),
    )
    assert exact.start == equivalent.start == START
    assert config_fingerprint(exact) == config_fingerprint(equivalent)
    with pytest.raises(ValidationError, match=ResourceRejectionCode.PERIOD_LIMIT_EXCEEDED.value):
        config(end=START + dt.timedelta(days=366, microseconds=1))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", "EURUSD"),
        ("strategy_id", "STRAT07"),
        ("profile_id", "operator"),
        ("initial_balance", Decimal("0")),
        ("initial_balance", Decimal("-1")),
        ("initial_balance", Decimal("NaN")),
        ("initial_balance", Decimal("Infinity")),
    ],
)
def test_config_rejects_invalid_authoritative_inputs(field, value):
    with pytest.raises(ValidationError):
        config(**{field: value})


@pytest.mark.parametrize("field", ["start", "end"])
def test_config_rejects_naive_datetime(field):
    with pytest.raises(ValidationError):
        config(**{field: START.replace(tzinfo=None)})


def test_config_rejects_non_increasing_period_and_extra_or_limit_overrides():
    with pytest.raises(ValidationError):
        config(end=START)
    for override in ("max_candles", "max_events", "max_output_bytes", "max_active_runs", "page_size_override"):
        with pytest.raises(ValidationError):
            BacktestRunConfig(**config().model_dump(), **{override: 1})


@pytest.mark.parametrize(
    "field",
    ["spread_price", "slippage_price_per_side", "commission_usd_per_lot_per_side"],
)
@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")])
def test_costs_reject_negative_and_non_finite(field, value):
    with pytest.raises(ValidationError):
        costs(**{field: value})


def test_exact_governed_resource_policy_constants_and_no_override():
    assert (
        MAX_REQUESTED_PERIOD_DAYS,
        MAX_PRIMARY_REPLAY_EVENTS,
        MAX_TOTAL_CANDLE_INPUTS,
        MAX_ACTIVE_RUNS_PER_USER,
        MAX_ACTIVE_RUNS_SYSTEM,
        MAX_PENDING_RUNS,
        MAX_CANDIDATES_PER_RUN,
        MAX_TRADES_PER_RUN,
        MAX_EQUITY_POINTS_PER_RUN,
        MAX_ESTIMATED_OUTPUT_BYTES,
        MAX_API_PAGE_SIZE,
    ) == (366, 250_000, 1_000_000, 1, 2, 8, 100_000, 100_000, 250_000, 128 * 1024 * 1024, 500)
    with pytest.raises(ValidationError):
        BacktestResourcePolicy(max_total_candle_inputs=1_000_001)


def usage(**changes) -> ResourceUsage:
    values = {
        "primary_replay_events": 250_000,
        "total_candle_inputs": 1_000_000,
        "active_runs_for_user": 0,
        "active_runs_system": 0,
        "pending_runs": 0,
        "candidate_count": 100_000,
        "trade_count": 100_000,
        "equity_point_count": 250_000,
        "estimated_output_bytes": 128 * 1024 * 1024,
    }
    values.update(changes)
    return ResourceUsage(**values)


def test_resource_counter_boundaries_and_stable_rejections():
    assert validate_resource_usage(usage()).accepted
    result = validate_resource_usage(
        usage(
            primary_replay_events=250_001,
            total_candle_inputs=1_000_001,
            active_runs_for_user=1,
            active_runs_system=2,
            pending_runs=8,
            candidate_count=100_001,
            trade_count=100_001,
            equity_point_count=250_001,
            estimated_output_bytes=128 * 1024 * 1024 + 1,
        )
    )
    assert not result.accepted
    assert set(result.rejection_codes) == set(ResourceRejectionCode) - {ResourceRejectionCode.PERIOD_LIMIT_EXCEEDED}
    with pytest.raises(ValidationError):
        usage(candidate_count=-1)


@pytest.mark.parametrize(
    ("changes", "accepted"),
    [
        ({"active_runs_for_user": 0}, True),
        ({"active_runs_for_user": 1}, False),
        ({"active_runs_system": 1}, True),
        ({"active_runs_system": 2}, False),
        ({"pending_runs": 7}, True),
        ({"pending_runs": 8}, False),
        ({"estimated_output_bytes": MAX_ESTIMATED_OUTPUT_BYTES}, True),
        ({"estimated_output_bytes": MAX_ESTIMATED_OUTPUT_BYTES + 1}, False),
    ],
)
def test_admission_counters_are_existing_pre_admission_counts(changes, accepted):
    baseline = {
        "primary_replay_events": 0,
        "total_candle_inputs": 0,
        "active_runs_for_user": 0,
        "active_runs_system": 0,
        "pending_runs": 0,
        "candidate_count": 0,
        "trade_count": 0,
        "equity_point_count": 0,
        "estimated_output_bytes": 0,
    }
    baseline.update(changes)
    assert validate_resource_usage(ResourceUsage(**baseline)).accepted is accepted


def test_typed_gap_validation_and_scheduled_closure():
    scheduled = CoverageGap(
        timeframe=Timeframe.M5,
        gap_start=START,
        gap_end=START + dt.timedelta(days=2),
        code=CoverageGapCode.SCHEDULED_MARKET_CLOSURE,
        expectation=GapExpectation.EXPECTED_SCHEDULED_CLOSURE,
    )
    assert coverage(gaps=(scheduled,)).status is CoverageStatus.SUFFICIENT
    with pytest.raises(ValidationError):
        CoverageGap(**{**scheduled.model_dump(), "gap_end": START})
    with pytest.raises(ValidationError):
        CoverageGap(
            timeframe=Timeframe.M5,
            gap_start=START,
            gap_end=END,
            code=CoverageGapCode.MISSING_CANDLES,
            expectation=GapExpectation.EXPECTED_SCHEDULED_CLOSURE,
        )


def test_coverage_is_fail_closed_for_shortfall_gap_and_news():
    unexpected = CoverageGap(
        timeframe=Timeframe.M5,
        gap_start=START,
        gap_end=START + dt.timedelta(minutes=5),
        code=CoverageGapCode.MISSING_CANDLES,
        expectation=GapExpectation.UNEXPECTED,
    )
    with pytest.raises(ValidationError, match="causal coverage shortfall"):
        coverage(gaps=(unexpected,))
    with pytest.raises(ValidationError, match="causal coverage shortfall"):
        coverage_with_shortfall()
    with pytest.raises(ValidationError, match="causal coverage shortfall"):
        coverage(news_vintages=news_coverage(required=True, available=False))
    insufficient = coverage_with_shortfall(CoverageStatus.INSUFFICIENT)
    with pytest.raises(ValidationError, match="SUFFICIENT coverage"):
        manifest(cov=insufficient)


def test_coverage_rejects_malformed_ranges_counts_and_frames():
    with pytest.raises(ValidationError):
        coverage(usable_start=WARMUP - dt.timedelta(seconds=1))
    with pytest.raises(ValidationError):
        coverage(total_candle_inputs=-1)
    with pytest.raises(ValidationError):
        coverage(required_timeframes=(Timeframe.M5, Timeframe.H1))
    with pytest.raises(ValidationError, match="Mixed market data sources"):
        coverage(
            timeframe_coverage=(
                TimeframeCoverage(
                    timeframe=Timeframe.M5,
                    available_start=WARMUP,
                    available_end=END,
                    requested_events=8_928,
                    available_events=8_928,
                    source="different_source",
                ),
            )
        )
    with pytest.raises(ValidationError, match="Primary event counts"):
        coverage(requested_primary_events=8_927)
    with pytest.raises(ValidationError):
        TimeframeCoverage(
            timeframe=Timeframe.M5,
            available_start=END,
            available_end=START,
            requested_events=1,
            available_events=1,
            source="fixture_market_v1",
        )


@pytest.mark.parametrize("strategy_id", ["STRAT05", "STRAT06"])
def test_news_strategy_manifest_requires_full_causal_vintage_coverage(strategy_id):
    cfg = config(strategy_id=strategy_id, profile_id="news")
    with pytest.raises(ValidationError, match="causal historical news vintages"):
        manifest(cfg=cfg, cov=coverage(news_vintages=news_coverage(required=False, available=True)))
    with pytest.raises(ValidationError, match="causal coverage shortfall"):
        manifest(cfg=cfg, cov=coverage(news_vintages=news_coverage(required=True, available=False)))
    with pytest.raises(ValidationError, match="cover the requested period"):
        coverage(
            news_vintages=NewsVintageCoverage(
                required=True,
                available=True,
                source="fixture_news_vintage_v1",
                vintage_start=START + dt.timedelta(days=1),
                vintage_end=END,
                availability_verified_at=END,
            )
        )
    with pytest.raises(ValidationError, match="cover the requested period"):
        coverage(
            news_vintages=NewsVintageCoverage(
                required=True,
                available=True,
                source="fixture_news_vintage_v1",
                vintage_start=WARMUP,
                vintage_end=END - dt.timedelta(days=1),
                availability_verified_at=END,
            )
        )
    accepted = manifest(cfg=cfg, cov=coverage(news_vintages=news_coverage(required=True, available=True)))
    assert accepted.coverage.news_vintages.required
    assert accepted.coverage.news_vintages.available


def test_non_news_strategy_remains_valid_without_required_news():
    assert manifest().config.strategy_id == "STRAT01"


def test_manifest_rejects_primary_timeframe_mismatch_even_when_both_frames_are_covered():
    m5 = TimeframeCoverage(
        timeframe=Timeframe.M5,
        available_start=WARMUP,
        available_end=END,
        requested_events=8_928,
        available_events=8_928,
        source="fixture_market_v1",
    )
    h1 = TimeframeCoverage(
        timeframe=Timeframe.H1,
        available_start=WARMUP,
        available_end=END,
        requested_events=744,
        available_events=744,
        source="fixture_market_v1",
    )
    cov = coverage(
        timeframe=Timeframe.H1,
        requested_primary_events=744,
        available_primary_events=744,
        total_candle_inputs=9_672,
        required_timeframes=(Timeframe.M5, Timeframe.H1),
        timeframe_coverage=(m5, h1),
    )
    with pytest.raises(ValidationError, match="primary timeframes must match"):
        manifest(cfg=config(timeframe=Timeframe.M5), cov=cov)

    matching = manifest(
        cfg=config(timeframe=Timeframe.H1),
        cov=cov,
    )
    assert matching.config.timeframe is matching.coverage.timeframe is Timeframe.H1


def test_manifest_detects_fingerprint_and_provenance_mismatch():
    with pytest.raises(ValidationError, match="Configuration fingerprint"):
        manifest(configuration_fingerprint="b" * 64)
    with pytest.raises(ValidationError, match="Coverage fingerprint"):
        manifest(data_coverage_fingerprint="b" * 64)
    with pytest.raises(ValidationError, match="Data fingerprint"):
        manifest(data_fingerprint="b" * 64)
    with pytest.raises(ValidationError, match="market source"):
        manifest(market_source="different_fixture")


def test_golden_canonical_json_and_sha_are_independently_calculated():
    value = {
        "when": dt.datetime(2026, 9, 23, 15, 0, tzinfo=dt.timezone(dt.timedelta(hours=7))),
        "amount": Decimal("10000.00"),
        "costs": costs(),
        "strategy": "STRAT01",
    }
    expected_json = (
        '{"amount":"10000","costs":{"commission_usd_per_lot_per_side":"3.5",'
        '"slippage_price_per_side":"0.01","spread_price":"0.3"},"strategy":"STRAT01",'
        '"when":"2026-09-23T08:00:00.000000Z"}'
    )
    expected_sha = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
    assert canonical_json(value) == expected_json
    assert semantic_fingerprint(value) == expected_sha


def test_decimal_numeric_equivalence_and_key_order_are_non_semantic():
    assert semantic_fingerprint({"a": Decimal("0.30"), "b": Decimal("0.010")}) == semantic_fingerprint(
        {"b": Decimal("0.01"), "a": Decimal("0.3")}
    )
    with pytest.raises(TypeError, match="Float"):
        semantic_fingerprint({"money": 0.3})


@pytest.mark.parametrize(
    "mutation",
    [
        lambda: manifest(
            cfg=config(end=END + dt.timedelta(days=1)),
            cov=coverage(
                requested_end=END + dt.timedelta(days=1),
                usable_end=END + dt.timedelta(days=1),
                requested_primary_events=9_216,
                available_primary_events=9_216,
                total_candle_inputs=46_080,
                timeframe_coverage=(
                    TimeframeCoverage(
                        timeframe=Timeframe.M5,
                        available_start=WARMUP,
                        available_end=END + dt.timedelta(days=1),
                        requested_events=9_216,
                        available_events=9_216,
                        source="fixture_market_v1",
                    ),
                ),
            ),
        ),
        lambda: manifest(
            cfg=config(timeframe=Timeframe.M15),
            cov=coverage(
                timeframe=Timeframe.M15,
                requested_primary_events=2_976,
                available_primary_events=2_976,
                total_candle_inputs=14_880,
                required_timeframes=(Timeframe.M15,),
                timeframe_coverage=(
                    TimeframeCoverage(
                        timeframe=Timeframe.M15,
                        available_start=WARMUP,
                        available_end=END,
                        requested_events=2_976,
                        available_events=2_976,
                        source="fixture_market_v1",
                    ),
                ),
            ),
        ),
        lambda: manifest(cfg=config(strategy_id="STRAT02"), strategy_version="strategy-1.2.1"),
        lambda: manifest(cfg=config(profile_id="trend")),
        lambda: manifest(cfg=config(initial_balance=Decimal("20000"))),
        lambda: manifest(cfg=config(costs=costs(spread_price=Decimal("0.4")))),
        lambda: manifest(cov=coverage_with_source("fixture_market_v2"), market_source="fixture_market_v2"),
        lambda: manifest(cov=coverage(total_candle_inputs=44_641)),
        lambda: manifest(strategy_version="strategy-9.9.9"),
        lambda: manifest(risk_policy_version="risk-policy-9.9.9"),
    ],
)
def test_manifest_fingerprint_changes_for_semantic_mutations(mutation):
    assert run_input_fingerprint(mutation()) != run_input_fingerprint(manifest())


def test_layered_fingerprints_and_non_semantic_run_id_exclusion():
    item = manifest()
    assert len(config_fingerprint(item.config)) == 64
    assert len(coverage_fingerprint(item.coverage)) == 64
    assert len(data_provenance_fingerprint(item.provenance)) == 64
    assert len(resource_policy_fingerprint(BacktestResourcePolicy())) == 64
    semantic = run_input_fingerprint(item)
    envelope_a = BacktestRunEnvelope(
        run_id="bt_run_abcdefgh",
        semantic_fingerprint=semantic,
        status=RunLifecycle.CREATED,
        created_at=START,
    )
    envelope_b = envelope_a.model_copy(update={"run_id": "bt_run_ijklmnop"})
    assert envelope_a.semantic_fingerprint == envelope_b.semantic_fingerprint == semantic
    assert is_backtest_identity(envelope_a.run_id)
    assert not is_backtest_identity("risk_reservation_123")


def test_lifecycle_is_bounded_and_terminal_metadata_is_consistent():
    semantic = run_input_fingerprint(manifest())
    with pytest.raises(ValidationError):
        BacktestRunEnvelope(
            run_id="bt_run_abcdefgh",
            semantic_fingerprint=semantic,
            status="COMPLETED_WITH_DATA_GAPS",
            created_at=START,
        )
    with pytest.raises(ValidationError):
        BacktestRunEnvelope(
            run_id="live_run_abcdefgh",
            semantic_fingerprint=semantic,
            status=RunLifecycle.CREATED,
            created_at=START,
        )


@pytest.mark.parametrize(
    ("status", "metadata"),
    [
        (RunLifecycle.CREATED, {"failure_code": RunFailureCode.INTERNAL_FAILURE}),
        (RunLifecycle.CREATED, {"completed_at": END}),
        (RunLifecycle.CREATED, {"started_at": START}),
        (RunLifecycle.RUNNING, {}),
        (RunLifecycle.RUNNING, {"started_at": START, "completed_at": END}),
        (RunLifecycle.RUNNING, {"started_at": START, "failure_code": RunFailureCode.INTERNAL_FAILURE}),
        (RunLifecycle.COMPLETED, {"completed_at": END}),
        (RunLifecycle.COMPLETED, {"started_at": START}),
        (
            RunLifecycle.COMPLETED,
            {"started_at": START, "completed_at": END, "failure_code": RunFailureCode.INTERNAL_FAILURE},
        ),
        (RunLifecycle.FAILED, {"completed_at": END}),
        (RunLifecycle.FAILED, {"failure_code": RunFailureCode.INTERNAL_FAILURE}),
        (
            RunLifecycle.FAILED,
            {"completed_at": END, "failure_code": RunFailureCode.CANCELLED_BY_OWNER},
        ),
        (RunLifecycle.CANCELLED, {"completed_at": END}),
        (
            RunLifecycle.CANCELLED,
            {"completed_at": END, "failure_code": RunFailureCode.INTERNAL_FAILURE},
        ),
        (RunLifecycle.CANCELLED, {"failure_code": RunFailureCode.CANCELLED_BY_OWNER}),
    ],
)
def test_lifecycle_matrix_rejects_contradictory_metadata(status, metadata):
    with pytest.raises(ValidationError):
        BacktestRunEnvelope(
            run_id="bt_run_abcdefgh",
            semantic_fingerprint=run_input_fingerprint(manifest()),
            status=status,
            created_at=START,
            **metadata,
        )


@pytest.mark.parametrize(
    ("status", "metadata"),
    [
        (RunLifecycle.CREATED, {}),
        (RunLifecycle.RUNNING, {"started_at": START}),
        (RunLifecycle.COMPLETED, {"started_at": START, "completed_at": END}),
        (RunLifecycle.FAILED, {"completed_at": END, "failure_code": RunFailureCode.INTERNAL_FAILURE}),
        (
            RunLifecycle.CANCELLED,
            {"completed_at": END, "failure_code": RunFailureCode.CANCELLED_BY_SYSTEM},
        ),
    ],
)
def test_lifecycle_matrix_accepts_coherent_metadata_including_pre_start_terminal_states(status, metadata):
    item = BacktestRunEnvelope(
        run_id="bt_run_abcdefgh",
        semantic_fingerprint=run_input_fingerprint(manifest()),
        status=status,
        created_at=START,
        **metadata,
    )
    assert item.status is status


def test_d1_versions_are_server_owned_while_strategy_and_risk_versions_remain_inputs():
    item = manifest()
    assert item.contract_version == BACKTEST_CONTRACT_VERSION
    assert item.fingerprint_version == BACKTEST_FINGERPRINT_VERSION
    assert item.provenance.replay_engine_version == REPLAY_ENGINE_VERSION_PLACEHOLDER
    assert "not-implemented" in item.provenance.replay_engine_version

    with pytest.raises(ValidationError):
        manifest(backtest_contract_version="backtest-contract-9.9.9")
    with pytest.raises(ValidationError):
        BacktestRunManifest(**{**item.model_dump(), "fingerprint_version": "backtest-fingerprint-9.9.9"})
    with pytest.raises(ValidationError):
        manifest(replay_engine_version="replay-engine-implemented-9.9.9")

    assert run_input_fingerprint(manifest(strategy_version="strategy-9.9.9")) != run_input_fingerprint(item)
    assert run_input_fingerprint(manifest(risk_policy_version="risk-policy-9.9.9")) != run_input_fingerprint(item)


def test_set_like_coverage_and_provenance_order_is_canonical_and_fingerprint_invariant():
    m5 = TimeframeCoverage(
        timeframe=Timeframe.M5,
        available_start=WARMUP,
        available_end=END,
        requested_events=8_928,
        available_events=8_928,
        source="fixture_market_v1",
    )
    h1 = TimeframeCoverage(
        timeframe=Timeframe.H1,
        available_start=WARMUP,
        available_end=END,
        requested_events=744,
        available_events=744,
        source="fixture_market_v1",
    )
    gap_m5 = CoverageGap(
        timeframe=Timeframe.M5,
        gap_start=START,
        gap_end=START + dt.timedelta(hours=1),
        code=CoverageGapCode.SCHEDULED_MARKET_CLOSURE,
        expectation=GapExpectation.EXPECTED_SCHEDULED_CLOSURE,
    )
    gap_h1 = CoverageGap(
        timeframe=Timeframe.H1,
        gap_start=START + dt.timedelta(days=1),
        gap_end=START + dt.timedelta(days=2),
        code=CoverageGapCode.SCHEDULED_MARKET_CLOSURE,
        expectation=GapExpectation.EXPECTED_SCHEDULED_CLOSURE,
    )
    common = {
        "total_candle_inputs": 9_672,
        "required_timeframes": (Timeframe.M5, Timeframe.H1),
        "timeframe_coverage": (m5, h1),
        "gaps": (gap_m5, gap_h1),
    }
    forward = coverage(**common)
    reversed_coverage = coverage(
        **{
            **common,
            "required_timeframes": tuple(reversed(common["required_timeframes"])),
            "timeframe_coverage": tuple(reversed(common["timeframe_coverage"])),
            "gaps": tuple(reversed(common["gaps"])),
        }
    )
    assert forward == reversed_coverage
    assert coverage_fingerprint(forward) == coverage_fingerprint(reversed_coverage)

    forward_manifest = manifest(cov=forward)
    reverse_values = forward_manifest.provenance.model_dump()
    reverse_values["timeframes"] = tuple(reversed(forward_manifest.provenance.timeframes))
    reverse_values["data_coverage_fingerprint"] = coverage_fingerprint(reversed_coverage)
    reverse_provenance = BacktestProvenance(**reverse_values)
    reverse_manifest = BacktestRunManifest(
        config=forward_manifest.config,
        coverage=reversed_coverage,
        provenance=reverse_provenance,
        resource_policy_fingerprint=forward_manifest.resource_policy_fingerprint,
    )
    assert forward_manifest.provenance == reverse_manifest.provenance
    assert run_input_fingerprint(forward_manifest) == run_input_fingerprint(reverse_manifest)
    assert coverage_fingerprint(coverage(**{**common, "total_candle_inputs": 9_673})) != coverage_fingerprint(forward)


def test_canonical_json_preserves_genuinely_ordered_sequences():
    assert canonical_json({"events": ("second", "first")}) != canonical_json({"events": ("first", "second")})
