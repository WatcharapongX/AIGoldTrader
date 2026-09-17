"""Configuration compatibility and resolution matrix test suite for safe_db_upgrade.

Verifies:
CASE A: DATABASE_URL present, POSTGRES_* absent -> uses DATABASE_URL.
CASE B: DATABASE_URL absent, complete POSTGRES_* -> resolves same effective URL as Settings.database_url.
CASE C: Both DATABASE_URL and complete POSTGRES_* -> same precedence as application Settings.
CASE D: DATABASE_URL absent, partial POSTGRES_* -> FAIL CLOSED.
CASE E: DATABASE_URL absent, POSTGRES_* absent -> FAIL CLOSED.
CASE F: DATABASE_URL_OVERRIDE present in operational resolution -> FAIL CLOSED.
CASE G: Explicit --db-url supplied -> uses explicit URL intentionally.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.scripts.safe_db_upgrade import (
    resolve_upgrade_database_url,
    run_safe_upgrade,
)


@pytest.fixture(autouse=True)
def clean_operational_env(monkeypatch: pytest.MonkeyPatch):
    """Ensures each test runs without ambient test-override environment variables."""
    monkeypatch.delenv("DATABASE_URL_OVERRIDE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for k in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        monkeypatch.delenv(k, raising=False)


# ==============================================================================
# CASE A: DATABASE_URL present, POSTGRES_* absent
# ==============================================================================


def test_case_a_database_url_present_postgres_absent():
    """CASE A: Uses DATABASE_URL when present and POSTGRES_* absent."""
    url = "postgresql://case_a_user:case_a_pass@case_a_host:5432/case_a_db"
    settings = Settings(DATABASE_URL=url, _env_file=None)

    resolved = resolve_upgrade_database_url(settings_factory=lambda: settings)

    assert "case_a_user:case_a_pass@case_a_host:5432/case_a_db" in resolved
    assert resolved == settings.database_url


# ==============================================================================
# CASE B: DATABASE_URL absent, complete POSTGRES_* present
# ==============================================================================


def test_case_b_database_url_absent_complete_postgres():
    """CASE B: Resolves same effective URL as Settings.database_url when POSTGRES_* complete."""
    settings = Settings(
        postgres_host="case_b_host",
        postgres_port=5433,
        postgres_db="case_b_db",
        postgres_user="case_b_user",
        postgres_password="case_b_password",
        _env_file=None,
    )

    resolved = resolve_upgrade_database_url(settings_factory=lambda: settings)

    assert resolved == settings.database_url
    assert "case_b_user:case_b_password@case_b_host:5433/case_b_db" in resolved


# ==============================================================================
# CASE C: Both DATABASE_URL and complete POSTGRES_* present
# ==============================================================================


def test_case_c_both_database_url_and_complete_postgres():
    """CASE C: Follows application Settings precedence (DATABASE_URL takes precedence)."""
    url = "postgresql://precedence_user:precedence_pass@precedence_host:5432/precedence_db"
    settings = Settings(
        DATABASE_URL=url,
        postgres_host="other_host",
        postgres_port=5433,
        postgres_db="other_db",
        postgres_user="other_user",
        postgres_password="other_password",
        _env_file=None,
    )

    resolved = resolve_upgrade_database_url(settings_factory=lambda: settings)

    assert resolved == settings.database_url
    assert "precedence_user" in resolved
    assert "other_user" not in resolved


# ==============================================================================
# CASE D: DATABASE_URL absent, partial POSTGRES_* present
# ==============================================================================


@pytest.mark.parametrize(
    "partial_kwargs",
    [
        {"postgres_host": "host_only"},
        {"postgres_host": "host", "postgres_port": 5432},
        {"postgres_host": "host", "postgres_port": 5432, "postgres_db": "db"},
        {"postgres_host": "host", "postgres_port": 5432, "postgres_db": "db", "postgres_user": "u"},
        # missing password:
        {"postgres_host": "h", "postgres_port": 5432, "postgres_db": "d", "postgres_user": "u"},
        # missing port:
        {"postgres_host": "h", "postgres_db": "d", "postgres_user": "u", "postgres_password": "p"},
    ],
)
def test_case_d_partial_postgres_fails_closed(partial_kwargs):
    """CASE D: Partial POSTGRES_* configuration fails closed without fabricating defaults."""
    settings = Settings(**partial_kwargs, _env_file=None)

    with pytest.raises(ValueError, match="Set DATABASE_URL or all POSTGRES_\\* connection settings"):
        resolve_upgrade_database_url(settings_factory=lambda: settings)

    rc = run_safe_upgrade(settings_factory=lambda: settings)
    assert rc == 1


# ==============================================================================
# CASE E: DATABASE_URL absent, POSTGRES_* absent
# ==============================================================================


def test_case_e_no_db_config_fails_closed():
    """CASE E: No database configuration fails closed."""
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="Set DATABASE_URL or all POSTGRES_\\* connection settings"):
        resolve_upgrade_database_url(settings_factory=lambda: settings)

    rc = run_safe_upgrade(settings_factory=lambda: settings)
    assert rc == 1


# ==============================================================================
# CASE F: DATABASE_URL_OVERRIDE present in operational resolution
# ==============================================================================


def test_case_f_database_url_override_fails_closed(monkeypatch: pytest.MonkeyPatch):
    """CASE F: DATABASE_URL_OVERRIDE fails closed to prevent silent redirection."""
    monkeypatch.setenv("DATABASE_URL_OVERRIDE", "sqlite+aiosqlite:///:memory:")
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="DATABASE_URL_OVERRIDE is reserved for isolated testing"):
        resolve_upgrade_database_url(settings_factory=lambda: settings)

    rc = run_safe_upgrade(settings_factory=lambda: settings)
    assert rc == 1


# ==============================================================================
# CASE G: Explicit --db-url supplied
# ==============================================================================


def test_case_g_explicit_db_url_used_intentionally():
    """CASE G: Explicit db-url is used directly regardless of Settings."""
    explicit = "postgresql://explicit_user:explicit_pass@explicit_host:5432/explicit_db"

    # Settings configured empty
    settings = Settings(_env_file=None)

    resolved = resolve_upgrade_database_url(
        explicit_db_url=explicit,
        settings_factory=lambda: settings,
    )

    assert resolved == explicit


# ==============================================================================
# Zero Mutation & Secret Safety in safe_db_upgrade
# ==============================================================================


def test_failed_resolution_aborts_before_normalizer_and_alembic():
    """When resolution fails, normalizer and alembic subprocess are never invoked."""
    settings = Settings(_env_file=None)

    with (
        patch("app.scripts.safe_db_upgrade.normalize_0012_database") as mock_norm,
        patch("subprocess.run") as mock_subproc,
    ):
        rc = run_safe_upgrade(settings_factory=lambda: settings)

        assert rc == 1
        mock_norm.assert_not_called()
        mock_subproc.assert_not_called()


def test_successful_resolution_runs_safe_upgrade():
    """Successful resolution proceeds through upgrade workflow."""
    settings = Settings(
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="testdb",
        postgres_user="testuser",
        postgres_password="testpassword",
        _env_file=None,
    )

    mock_conn = MagicMock()
    mock_subproc = MagicMock(returncode=0, stdout="Alembic head reached", stderr="")

    with (
        patch("psycopg.connect") as mock_connect,
        patch("app.scripts.safe_db_upgrade.get_current_revision", return_value="0015_batch_a3_risk_account_fk"),
        patch("subprocess.run", return_value=mock_subproc) as mock_sub,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn

        rc = run_safe_upgrade(settings_factory=lambda: settings)

        assert rc == 0
        mock_sub.assert_called_once()
