"""Exact Migration Revision Guard Test Suite (Correction Batch A.3.1).

Verifies strict exact-string revision matching:
- REV_0012 = "0012_phase5_reconciliation" -> ALLOW / NORMALIZER REQUIRED
- REV_0013 = "0013_batch_a_risk_authority" -> SKIP NORMALIZER
- REV_0014 = "0014_batch_a2_account_authority" -> SKIP NORMALIZER
- REV_0015 = "0015_batch_a3_risk_account_fk" -> SKIP NORMALIZER
- REV_0016 = "0016_batch_b_refresh_families" -> SKIP NORMALIZER

All unsupported / invalid / unknown revisions must FAIL CLOSED:
- 0012_unknown -> FAIL
- 0012_bad_revision -> FAIL
- 0013_unknown -> FAIL
- 0014_unknown -> FAIL
- 0015_unknown -> FAIL
- 0011_phase... -> FAIL
- 0016_future -> FAIL
- missing alembic_version -> FAIL
- empty alembic_version -> FAIL
- multiple version rows -> FAIL

Zero Mutation Guarantee:
- Normalizer not invoked for unsupported revisions
- Alembic subprocess not invoked for unsupported revisions
- Returns exit code 1
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from app.scripts.normalize_0012_accounts import (
    REV_0012,
    REV_0013,
    REV_0014,
    REV_0015,
    REV_0016,
    normalize_0012_database,
)
from app.scripts.safe_db_upgrade import (
    classify_revision_action,
    run_safe_upgrade,
)

# ==============================================================================
# 1. safe_db_upgrade: classify_revision_action Tests
# ==============================================================================


def test_classify_revision_action_exact_matches():
    """Exact canonical revisions are correctly mapped."""
    assert classify_revision_action(REV_0012) == "NORMALIZE_THEN_UPGRADE"
    assert classify_revision_action(REV_0013) == "UPGRADE_ONLY"
    assert classify_revision_action(REV_0014) == "UPGRADE_ONLY"
    assert classify_revision_action(REV_0015) == "UPGRADE_ONLY"
    assert classify_revision_action(REV_0016) == "UPGRADE_ONLY"


@pytest.mark.parametrize(
    "unsupported_rev",
    [
        "0012_unknown",
        "0012_bad_revision",
        "0013_unknown",
        "0014_unknown",
        "0015_unknown",
        "0011_economic_actual_coverage",
        "0011_phase5_final_acceptance",
        "0016_future_migration",
        "0017_next",
        "random_revision",
        "",
        None,
    ],
)
def test_classify_revision_action_unsupported_rejections(unsupported_rev):
    """All non-canonical / prefix-matching variations fail closed as UNSUPPORTED."""
    assert classify_revision_action(unsupported_rev) == "UNSUPPORTED"


# ==============================================================================
# 2. normalize_0012_accounts: normalize_0012_database Revision Guard Tests
# ==============================================================================


@pytest.fixture
def sqlite_conn():
    """In-memory SQLite connection with alembic_version and accounts tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);")
    conn.execute("CREATE TABLE accounts (id VARCHAR(36) PRIMARY KEY, name VARCHAR(255));")
    conn.execute("CREATE TABLE paper_account_states (account_id VARCHAR(255));")
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def test_normalizer_exact_0012_allowed(sqlite_conn):
    """Exact REV_0012 allows normalizer to run."""
    sqlite_conn.execute("INSERT INTO alembic_version VALUES (?)", (REV_0012,))
    sqlite_conn.commit()

    res = normalize_0012_database(sqlite_conn)
    assert res["status"] == "CLEAN"
    assert res["normalized_aliases"] == 0


@pytest.mark.parametrize("upgraded_rev", [REV_0013, REV_0014, REV_0015, REV_0016])
def test_normalizer_exact_upgraded_skipped(sqlite_conn, upgraded_rev):
    """Exact REV_0013, REV_0014, REV_0015 skip normalizer safely."""
    sqlite_conn.execute("INSERT INTO alembic_version VALUES (?)", (upgraded_rev,))
    sqlite_conn.commit()

    res = normalize_0012_database(sqlite_conn)
    assert res["status"] == "SKIPPED"
    assert upgraded_rev in res["reason"]
    assert res["normalized_aliases"] == 0


@pytest.mark.parametrize(
    "bad_rev",
    [
        "0012_unknown",
        "0012_bad_revision",
        "0013_unknown",
        "0014_unknown",
        "0015_unknown",
        "0011_economic_actual_coverage",
        "0011_phase5_final_acceptance",
        "0016_future_migration",
        "0010_base",
    ],
)
def test_normalizer_rejects_unsupported_revisions(sqlite_conn, bad_rev):
    """Prefix matches and unknown revisions fail closed with RuntimeError."""
    sqlite_conn.execute("INSERT INTO alembic_version VALUES (?)", (bad_rev,))
    sqlite_conn.commit()

    with pytest.raises(RuntimeError, match=f"unsupported database revision '{bad_rev}'"):
        normalize_0012_database(sqlite_conn)


def test_normalizer_rejects_missing_alembic_table():
    """Missing alembic_version table fails closed."""
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(RuntimeError, match="alembic_version table is missing"):
            normalize_0012_database(conn)
    finally:
        conn.close()


def test_normalizer_rejects_empty_alembic_table(sqlite_conn):
    """Empty alembic_version table fails closed."""
    with pytest.raises(RuntimeError, match="alembic_version table is empty"):
        normalize_0012_database(sqlite_conn)


def test_normalizer_rejects_multiple_version_rows(sqlite_conn):
    """Multiple rows in alembic_version table fail closed."""
    sqlite_conn.execute("INSERT INTO alembic_version VALUES (?)", (REV_0012,))
    sqlite_conn.execute("INSERT INTO alembic_version VALUES (?)", (REV_0013,))
    sqlite_conn.commit()

    with pytest.raises(RuntimeError, match="multiple alembic version rows detected"):
        normalize_0012_database(sqlite_conn)


def test_normalizer_rejects_empty_version_string(sqlite_conn):
    """Row with empty string revision fails closed."""
    sqlite_conn.execute("INSERT INTO alembic_version VALUES ('')")
    sqlite_conn.commit()

    with pytest.raises(RuntimeError, match="alembic_version table contains empty revision string"):
        normalize_0012_database(sqlite_conn)


# ==============================================================================
# 3. safe_db_upgrade: Zero Mutation & Subprocess Guarantees
# ==============================================================================


@pytest.mark.parametrize(
    "unsupported_rev",
    [
        "0012_unknown",
        "0012_bad_revision",
        "0013_unknown",
        "0014_unknown",
        "0015_unknown",
        "0011_economic_actual_coverage",
        "0016_future_migration",
        None,
    ],
)
def test_safe_db_upgrade_aborts_without_mutation_or_subprocess(unsupported_rev):
    """Unsupported revisions abort before normalizer and before Alembic subprocess."""
    mock_conn = MagicMock()

    with (
        patch("psycopg.connect") as mock_connect,
        patch("app.scripts.safe_db_upgrade.get_current_revision", return_value=unsupported_rev),
        patch("app.scripts.safe_db_upgrade.normalize_0012_database") as mock_norm,
        patch("subprocess.run") as mock_subproc,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn

        rc = run_safe_upgrade(db_url="postgresql://user:pass@localhost:5432/testdb")

        assert rc == 1
        mock_norm.assert_not_called()
        mock_subproc.assert_not_called()
        mock_conn.commit.assert_not_called()


def test_safe_db_upgrade_aborts_on_multiple_version_rows():
    """Multiple revision rows abort before normalizer and before Alembic subprocess."""
    mock_conn = MagicMock()

    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "app.scripts.safe_db_upgrade.get_current_revision",
            side_effect=RuntimeError("Multiple alembic version rows detected"),
        ),
        patch("app.scripts.safe_db_upgrade.normalize_0012_database") as mock_norm,
        patch("subprocess.run") as mock_subproc,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn

        rc = run_safe_upgrade(db_url="postgresql://user:pass@localhost:5432/testdb")

        assert rc == 1
        mock_norm.assert_not_called()
        mock_subproc.assert_not_called()
        mock_conn.commit.assert_not_called()


def test_safe_db_upgrade_invokes_normalizer_on_exact_0012():
    """Exact REV_0012 invokes normalizer in transaction then Alembic upgrade."""
    mock_conn = MagicMock()
    mock_subproc_result = MagicMock(returncode=0, stdout="Upgrade completed", stderr="")

    with (
        patch("psycopg.connect") as mock_connect,
        patch("app.scripts.safe_db_upgrade.get_current_revision", side_effect=[REV_0012, REV_0015]),
        patch("app.scripts.safe_db_upgrade.normalize_0012_database", return_value={"status": "CLEAN"}) as mock_norm,
        patch("subprocess.run", return_value=mock_subproc_result) as mock_subproc,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn

        rc = run_safe_upgrade(db_url="postgresql://user:pass@localhost:5432/testdb")

        assert rc == 0
        mock_norm.assert_called_once_with(mock_conn)
        mock_conn.commit.assert_called_once()
        mock_subproc.assert_called_once()


@pytest.mark.parametrize("upgraded_rev", [REV_0013, REV_0014, REV_0015, REV_0016])
def test_safe_db_upgrade_skips_normalizer_on_exact_upgraded(upgraded_rev):
    """Exact REV_0013, REV_0014, REV_0015 do NOT invoke normalizer, directly apply Alembic upgrade."""
    mock_conn = MagicMock()
    mock_subproc_result = MagicMock(returncode=0, stdout="Upgrade completed", stderr="")

    with (
        patch("psycopg.connect") as mock_connect,
        patch("app.scripts.safe_db_upgrade.get_current_revision", side_effect=[upgraded_rev, REV_0015]),
        patch("app.scripts.safe_db_upgrade.normalize_0012_database") as mock_norm,
        patch("subprocess.run", return_value=mock_subproc_result) as mock_subproc,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn

        rc = run_safe_upgrade(db_url="postgresql://user:pass@localhost:5432/testdb")

        assert rc == 0
        mock_norm.assert_not_called()
        mock_conn.commit.assert_not_called()
        mock_subproc.assert_called_once()
