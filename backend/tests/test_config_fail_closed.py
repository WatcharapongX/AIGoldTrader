"""Fail-closed trading/CORS configuration (Phase 1 security hardening)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_live_auto_trading_true_is_rejected():
    with pytest.raises(ValidationError, match="LIVE_AUTO_TRADING"):
        Settings(_env_file=None, live_auto_trading=True)


def test_trading_mode_live_is_rejected():
    with pytest.raises(ValidationError, match="TRADING_MODE=LIVE"):
        Settings(_env_file=None, trading_mode="LIVE")


def test_wildcard_cors_is_rejected():
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        Settings(_env_file=None, cors_origins="*")


def test_paper_defaults_are_accepted():
    settings = Settings(_env_file=None)
    assert settings.trading_mode == "PAPER"
    assert settings.live_auto_trading is False
