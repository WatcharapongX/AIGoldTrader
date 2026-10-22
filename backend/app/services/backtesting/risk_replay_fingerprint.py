"""Separate complete-input and causal-output D2C identities."""

from decimal import Decimal

from app.services.backtesting.fingerprint import semantic_fingerprint
from app.services.backtesting.risk_replay_domain import RISK_REPLAY_INTEGRATION_VERSION, RiskReplayConfig


def risk_configuration_fingerprint(config: RiskReplayConfig) -> str:
    return semantic_fingerprint(
        {
            "kind": "risk-replay-configuration",
            "integration_version": RISK_REPLAY_INTEGRATION_VERSION,
            "config": config,
            "semantics": {
                "account": "INITIAL_BALANCE_RESET_CONFIGURED_TEST_BACKTEST",
                "portfolio": "ZERO_EXPOSURE_RESET_INTEGRITY_OK",
                "account_identity": "VERSION_SYMBOL_BALANCE_RISK_CONFIG_ONLY",
                "kill_switch": "BACKTEST_NO_EXTERNAL_KILL_SWITCH",
                "data_health": "BACKTEST_CAUSAL_DATA_ADMISSION",
                "candidate_transition_count": 0,
                "eligibility": "ONE_RECORD_PER_STRATEGY_EVENT_PLAN_ONLY_EVALUATION",
                "quote": "LATEST_TIMESTAMP_WITH_TIMESTAMP_AND_OBSERVED_AT_LE_T",
                "news": "ALL_STRATEGIES_REQUIRE_HISTORICAL_LIVE_VINTAGES_WHEN_ENABLED",
                "news_projection": "NEWS_ENGINE_LATEST_KNOWN_MAX_200_DISABLED_UNAVAILABLE",
                "spec": "SCENARIO_EFFECTIVE_AT_T_NOT_BROKER_OBSERVATION",
                "requested_risk": "NONE_OR_FINITE_0_TO_100_MAX_12_DIGITS_8_DECIMALS",
            },
        }
    )


def baseline_account_id(symbol: str, initial_balance: Decimal, configuration_fingerprint: str) -> str:
    return "bt_acc_" + semantic_fingerprint(
        {
            "kind": "risk-replay-account-seed",
            "integration_version": RISK_REPLAY_INTEGRATION_VERSION,
            "symbol": symbol,
            "initial_balance": initial_balance,
            "risk_configuration_fingerprint": configuration_fingerprint,
        }
    )


def risk_replay_input_fingerprint(source_input: str, configuration: str) -> str:
    return semantic_fingerprint(
        {
            "kind": "risk-replay-input",
            "integration_version": RISK_REPLAY_INTEGRATION_VERSION,
            "source_replay_input_fingerprint": source_input,
            "risk_configuration_fingerprint": configuration,
        }
    )


def risk_event_fingerprint(payload: dict) -> str:
    return semantic_fingerprint(
        {"kind": "risk-replay-event", "integration_version": RISK_REPLAY_INTEGRATION_VERSION, **payload}
    )


def risk_output_fingerprint(payload: dict) -> str:
    return semantic_fingerprint(
        {"kind": "risk-replay-output", "integration_version": RISK_REPLAY_INTEGRATION_VERSION, **payload}
    )
