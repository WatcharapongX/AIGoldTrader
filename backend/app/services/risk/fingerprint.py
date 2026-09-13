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


def compute_evaluation_intent_identity(
    candidate: SetupCandidate,
    plan: TradePlanSuggestion,
    profile_id: str,
    account_id: str,
    requested_risk_pct: Decimal,
) -> str:
    """Computes a stable identity for the evaluation intent, independent of live market jitter."""
    intent_obj = {
        "account_id": account_id,
        "candidate_id": candidate.id,
        "strategy_id": candidate.strategy_id,
        "symbol": candidate.symbol,
        "profile_id": profile_id,
        "plan_id": plan.id,
        "direction": plan.direction,
        "entry_lower": format(Decimal(str(plan.entry_lower)), ".5f"),
        "entry_upper": format(Decimal(str(plan.entry_upper)), ".5f"),
        "stop_loss": format(Decimal(str(plan.stop_loss)), ".5f"),
        "requested_risk_pct": format(requested_risk_pct, ".4f"),
    }
    serialized = json.dumps(intent_obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
    account_is_stale: bool = False,
    quote_is_stale: bool = False,
    plan_is_expired: bool = False,
    cooldown_active: bool = False,
) -> str:
    """Computes a canonical SHA-256 fingerprint representing the exact semantic safety state.

    Any change to candidate geometry, account snapshot, quote, news status, Kill Switch state,
    symbol spec, policy version, portfolio budget, or temporal safety validity alters the fingerprint,
    guaranteeing safe re-evaluation. Volatile quote arrival microsecond jitter is excluded.
    """
    # Derive semantic market risk state without raw bid/ask price jitter (SOL High Round 3 Section 9)
    if quote is None:
        market_safety_state = "UNAVAILABLE"
        spread_band = "UNKNOWN"
        quote_payload = {
            "source": "none",
            "mode": "none",
            "market_safety_state": market_safety_state,
            "spread_band": spread_band,
            "is_stale": True,
        }
    else:
        in_post_news = bool(news_prov and news_prov.in_post_news_window)
        if quote_is_stale:
            market_safety_state = "STALE"
        elif quote.spread > policy.max_spread_absolute:
            market_safety_state = "SPREAD_BLOCKED"
        elif in_post_news and quote.spread > policy.max_spread_absolute * Decimal("0.8"):
            market_safety_state = "POST_NEWS_SPREAD_BLOCKED"
        else:
            market_safety_state = "AVAILABLE_SAFE"

        if quote.spread <= policy.max_spread_absolute * Decimal("0.8"):
            spread_band = "ACCEPTABLE"
        elif quote.spread <= policy.max_spread_absolute:
            spread_band = "ELEVATED"
        else:
            spread_band = "EXCESSIVE"

        quote_payload = {
            "source": quote.source,
            "mode": quote.mode,
            "market_safety_state": market_safety_state,
            "spread_band": spread_band,
            "is_stale": quote_is_stale,
        }

    news_payload = None
    if news_prov:
        prov = getattr(news_prov, "provider", "") or getattr(news_prov, "source", "")
        rev = getattr(news_prov, "revision_id", "") or (
            str(getattr(news_prov, "revision_version", ""))
            if getattr(news_prov, "revision_version", None) is not None
            else ""
        )
        news_payload = {
            "provider": prov,
            "source": getattr(news_prov, "source", "") or prov,
            "revision_id": rev,
            "revision_version": getattr(news_prov, "revision_version", None),
            "news_state": news_prov.news_state,
            "in_blackout": news_prov.in_blackout,
            "in_pre_news_window": news_prov.in_pre_news_window,
            "in_post_news_window": news_prov.in_post_news_window,
            "event_ids": sorted(news_prov.event_ids),
            "description_th": news_prov.description_th,
            "events": [
                {
                    "provider": getattr(e, "provider", "") or getattr(e, "source", ""),
                    "source": getattr(e, "source", "") or getattr(e, "provider", ""),
                    "event_id": e.event_id,
                    "event_name": e.event_name,
                    "currency": e.currency,
                    "impact": e.impact,
                    "scheduled_at": e.scheduled_at.isoformat(),
                    "available_at": e.available_at.isoformat() if e.available_at is not None else None,
                    "revision_id": getattr(e, "revision_id", "")
                    or (
                        str(getattr(e, "revision_version", ""))
                        if getattr(e, "revision_version", None) is not None
                        else ""
                    ),
                    "revision_version": getattr(e, "revision_version", None),
                    "window_state": e.window_state,
                }
                for e in news_prov.events
            ],
        }

    plan_payload = {
        "id": plan.id,
        "direction": plan.direction,
        "entry_lower": format(Decimal(str(plan.entry_lower)), ".5f"),
        "entry_upper": format(Decimal(str(plan.entry_upper)), ".5f"),
        "stop_loss": format(Decimal(str(plan.stop_loss)), ".5f"),
        "score": candidate.score,
        "risk_reward": (
            format(Decimal(str(plan.risk_reward)), ".2f")
            if hasattr(plan, "risk_reward") and plan.risk_reward is not None
            else None
        ),
        "expires_at": plan.expires_at.isoformat() if plan.expires_at else None,
        "is_expired": plan_is_expired,
    }

    account_payload = {
        "account_id": account.account_id,
        "state_version": getattr(account, "state_version", 1),
        "balance": format(account.balance, ".2f"),
        "equity": format(account.equity, ".2f"),
        "free_margin": format(account.free_margin, ".2f") if account.free_margin is not None else None,
        "daily_realized_pnl": format(account.daily_realized_pnl, ".2f"),
        "weekly_realized_pnl": format(account.weekly_realized_pnl, ".2f"),
        "floating_pnl": format(account.floating_pnl, ".2f") if account.floating_pnl is not None else None,
        "peak_equity": format(account.peak_equity, ".2f"),
        "open_risk_pct": format(account.open_risk_pct, ".4f"),
        "reserved_risk_pct": format(account.reserved_risk_pct, ".4f"),
        "consecutive_losses": account.consecutive_losses,
        "last_loss_at": account.last_loss_at.isoformat() if account.last_loss_at else None,
        "cooldown_until": account.cooldown_until.isoformat() if account.cooldown_until else None,
        "cooldown_active": cooldown_active,
        "open_positions_count": account.open_positions_count,
        "source": account.source,
        "is_stale": account_is_stale,
    }

    canonical_obj = {
        "candidate": {
            "id": candidate.id,
            "strategy_id": candidate.strategy_id,
            "strategy_version": candidate.strategy_version,
            "symbol": candidate.symbol,
            "profile_id": profile_id,
        },
        "plan": plan_payload,
        "account": account_payload,
        "policy": policy.model_dump(mode="json"),
        "spec": spec.model_dump(mode="json"),
        "kill_switch": {
            "id": kill_switch.id,
            "state": kill_switch.state,
            "trigger_type": kill_switch.trigger_type,
            "activated_at": kill_switch.activated_at.isoformat() if kill_switch.activated_at else None,
        },
        "market": quote_payload,
        "news": news_payload,
        "portfolio": {
            "exposure_before": format(portfolio_exposure_before, ".4f"),
            "requested_risk_pct": format(requested_risk_pct, ".4f"),
        },
        "temporal_safety": {
            "account_is_stale": account_is_stale,
            "quote_is_stale": quote_is_stale,
            "plan_is_expired": plan_is_expired,
            "cooldown_active": cooldown_active,
        },
    }

    serialized = json.dumps(canonical_obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
