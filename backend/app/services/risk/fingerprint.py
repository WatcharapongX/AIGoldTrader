"""Phase 5 Dependency-aware deterministic risk fingerprint and identity calculator.

Excludes volatile request clock, arrival jitter, and random UUIDs.
Same semantic safety dependencies strictly yield the exact same decision fingerprint.
"""

import hashlib
import json
from decimal import Decimal

from app.services.market_data.domain import Quote
from app.services.risk.domain import (
    AccountSnapshot,
    KillSwitchState,
    NewsRiskProvenance,
    RiskPolicy,
    SymbolSpecification,
)
from app.services.strategy.domain import SetupCandidate, TradePlanSuggestion


def compute_risk_dependency_fingerprint(
    candidate: SetupCandidate,
    plan: TradePlanSuggestion,
    profile_id: str,
    account: AccountSnapshot,
    policy: RiskPolicy,
    spec: SymbolSpecification,
    kill_switch: KillSwitchState,
    quote: Quote | None,
    news_prov: NewsRiskProvenance | None,
    portfolio_exposure_before: Decimal,
    requested_risk_pct: Decimal,
) -> str:
    """Computes a canonical SHA-256 fingerprint representing the exact semantic safety state.

    Any change to candidate geometry, account snapshot, quote, news status, Kill Switch state,
    symbol spec, policy version, or portfolio budget alters the fingerprint, guaranteeing
    safe re-evaluation.
    """
    quote_payload = None
    if quote:
        quote_payload = {
            "source": quote.source,
            "mode": quote.mode,
            "bid": format(Decimal(str(quote.bid)), ".5f"),
            "ask": format(Decimal(str(quote.ask)), ".5f"),
            "spread": format(Decimal(str(quote.spread)), ".5f"),
            "timestamp": quote.timestamp.isoformat(),
        }

    news_payload = None
    if news_prov:
        news_payload = {
            "news_state": news_prov.news_state,
            "in_blackout": news_prov.in_blackout,
            "in_pre_news_window": news_prov.in_pre_news_window,
            "in_post_news_window": news_prov.in_post_news_window,
            "event_ids": sorted(news_prov.event_ids),
        }

    canonical_obj = {
        "candidate": {
            "id": candidate.id,
            "strategy_id": candidate.strategy_id,
            "strategy_version": candidate.strategy_version,
            "symbol": candidate.symbol,
            "profile_id": profile_id,
        },
        "plan": {
            "id": plan.id,
            "direction": plan.direction,
            "entry_lower": format(Decimal(str(plan.entry_lower)), ".5f"),
            "entry_upper": format(Decimal(str(plan.entry_upper)), ".5f"),
            "stop_loss": format(Decimal(str(plan.stop_loss)), ".5f"),
        },
        "account": {
            "id": account.id,
            "account_id": account.account_id,
            "equity": format(account.equity, ".2f"),
            "open_risk_pct": format(account.open_risk_pct, ".4f"),
            "as_of": account.as_of.isoformat(),
            "source": account.source,
        },
        "policy": {
            "version": policy.version,
            "max_risk_per_trade_pct": format(policy.max_risk_per_trade_pct, ".4f"),
            "max_account_risk_pct": format(policy.max_account_risk_pct, ".4f"),
            "max_symbol_risk_pct": format(policy.max_symbol_risk_pct, ".4f"),
            "max_directional_risk_pct": format(policy.max_directional_risk_pct, ".4f"),
            "max_concurrent_trades": policy.max_concurrent_trades,
            "daily_loss_limit_pct": format(policy.daily_loss_limit_pct, ".4f"),
            "max_spread_absolute": format(policy.max_spread_absolute, ".4f"),
            "news_reduction_factor": format(policy.news_reduction_factor, ".4f"),
        },
        "spec": {
            "id": spec.id,
            "symbol": spec.symbol,
            "source": spec.source,
            "tick_size": format(spec.tick_size, ".5f"),
            "volume_step": format(spec.volume_step, ".4f"),
            "observed_at": spec.observed_at.isoformat(),
        },
        "kill_switch": {
            "id": kill_switch.id,
            "state": kill_switch.state,
            "trigger_type": kill_switch.trigger_type,
            "activated_at": kill_switch.activated_at.isoformat(),
        },
        "market": quote_payload,
        "news": news_payload,
        "portfolio": {
            "exposure_before": format(portfolio_exposure_before, ".4f"),
            "requested_risk_pct": format(requested_risk_pct, ".4f"),
        },
    }

    serialized = json.dumps(canonical_obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
