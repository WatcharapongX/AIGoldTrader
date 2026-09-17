"""Canonical Safe Database Upgrade Tool.

Executes transactional pre-upgrade reconciliation (normalize_0012_database)
when the database is at revision 0012, then applies Alembic migrations up to head.
If the database is already at or past revision 0013, normalization is safely skipped.
Unsupported revisions fail closed without applying mutations.

Zero Credential Exposure: All connection URLs and logs mask sensitive secrets.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.scripts.normalize_0012_accounts import (
    KNOWN_UPGRADED_REVISIONS,
    REV_0012,
    normalize_0012_database,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("safe_db_upgrade")


def mask_url(url_str: str) -> str:
    """Masks password and credentials in connection URL."""
    try:
        u = make_url(url_str)
        return u.render_as_string(hide_password=True)
    except Exception:
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url_str)


def resolve_upgrade_database_url(
    explicit_db_url: str | None = None,
    settings_factory: Callable[[], Settings] | None = None,
) -> str:
    """Resolves the database URL for safe upgrade following application Settings authority.

    Resolution order:
    1. Explicit db_url parameter (e.g. from --db-url CLI flag).
    2. Normal application Settings resolution (supporting DATABASE_URL or complete POSTGRES_*).

    Invariants:
    - Fails closed if DATABASE_URL_OVERRIDE is present during normal operational resolution.
    - Fails closed if neither DATABASE_URL nor complete POSTGRES_* is available.
    - Fails closed if POSTGRES_* is incomplete.
    - Deterministically loads backend/.env if it exists.
    - Environment variables override .env values per normal application semantics.
    """
    if explicit_db_url and explicit_db_url.strip():
        return explicit_db_url.strip()

    if settings_factory is not None:
        settings = settings_factory()
    else:
        backend_dir = Path(__file__).resolve().parents[2]
        env_file = backend_dir / ".env"
        settings = Settings(_env_file=env_file if env_file.exists() else None)  # type: ignore[call-arg]

    if settings.database_url_override:
        raise ValueError(
            "DATABASE_URL_OVERRIDE is reserved for isolated testing and cannot be used "
            "for operational safe_db_upgrade. Use explicit --db-url if testing."
        )

    return settings.database_url


def get_current_revision(conn: psycopg.Connection) -> str | None:
    """Queries alembic_version table to determine current revision.

    Returns:
        str: Exact non-empty revision string.
        None: If alembic_version table does not exist or has no rows.

    Raises:
        RuntimeError: If multiple alembic version rows are detected.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('alembic_version');")
        res = cur.fetchone()
        if not res or res[0] is None:
            return None

        cur.execute("SELECT version_num FROM alembic_version;")
        rows = cur.fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise RuntimeError(f"Multiple alembic version rows detected: {[r[0] for r in rows]}")
        rev = str(rows[0][0]).strip()
        if not rev:
            return None
        return rev


def classify_revision_action(current_rev: str | None) -> str:
    """Classifies a database revision to determine safe upgrade action.

    Returns:
        "NORMALIZE_THEN_UPGRADE": if current_rev == REV_0012
        "UPGRADE_ONLY": if current_rev in KNOWN_UPGRADED_REVISIONS
        "UNSUPPORTED": for all other revisions (including None, empty, unknown, corrupt, or future revisions)
    """
    if current_rev == REV_0012:
        return "NORMALIZE_THEN_UPGRADE"
    if current_rev in KNOWN_UPGRADED_REVISIONS:
        return "UPGRADE_ONLY"
    return "UNSUPPORTED"


def run_safe_upgrade(
    db_url: str | None = None,
    settings_factory: Callable[[], Settings] | None = None,
) -> int:
    """Executes the safe upgrade workflow."""
    try:
        resolved_url = resolve_upgrade_database_url(db_url, settings_factory=settings_factory)
    except ValueError as cfg_err:
        logger.error("Database configuration error: %s. Failing closed.", cfg_err)
        return 1
    except Exception as err:
        logger.error("Failed to resolve database configuration: %s. Failing closed.", err)
        return 1

    masked = mask_url(resolved_url)
    logger.info("Starting safe database upgrade against %s", masked)

    url_obj = make_url(resolved_url)
    driver_less = url_obj.set(drivername="postgresql").render_as_string(hide_password=False)

    try:
        with psycopg.connect(driver_less, autocommit=False) as conn:
            try:
                current_rev = get_current_revision(conn)
            except RuntimeError as rev_err:
                logger.error("Failed to determine revision: %s. Failing closed.", rev_err)
                return 1

            logger.info("Current revision: %s", current_rev or "None (uninitialized/empty)")

            action = classify_revision_action(current_rev)
            if action == "NORMALIZE_THEN_UPGRADE":
                normalizer_required = True
                logger.info("Normalizer required: YES (exact revision %s detected)", current_rev)
            elif action == "UPGRADE_ONLY":
                normalizer_required = False
                logger.info("Normalizer required: NO (database already at or past %s)", current_rev)
            else:
                logger.error(
                    "Unsupported database revision '%s'. "
                    "Safe upgrade strictly supports exact '%s' (normalize) or exact %s (upgrade-only). Failing closed.",
                    current_rev,
                    REV_0012,
                    sorted(KNOWN_UPGRADED_REVISIONS),
                )
                return 1

            if normalizer_required:
                logger.info("Executing 0012 account normalization transaction...")
                try:
                    norm_result = normalize_0012_database(conn)
                    conn.commit()
                    logger.info("Normalizer result: %s", norm_result)
                except Exception as norm_err:
                    conn.rollback()
                    logger.error("Normalizer failed with error: %s. Rolled back all changes.", norm_err)
                    logger.error("Alembic upgrade aborted. Database left unchanged at revision %s.", current_rev)
                    return 1

    except Exception as conn_err:
        logger.error("Failed to connect or verify database: %s", conn_err)
        return 1

    backend_dir = Path(__file__).resolve().parents[2]
    alembic_ini = backend_dir / "alembic.ini"
    logger.info("Alembic upgrade starting to head using config %s ...", alembic_ini.name)

    env = {**os.environ, "DATABASE_URL": resolved_url}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Alembic upgrade failed:\n%s", result.stderr)
        return result.returncode

    if result.stdout:
        for line in result.stdout.strip().splitlines():
            logger.info("  [alembic] %s", line)

    try:
        with psycopg.connect(driver_less, autocommit=True) as conn:
            final_rev = get_current_revision(conn)
            logger.info("Final revision: %s", final_rev)
    except Exception as check_err:
        logger.warning("Could not verify final revision: %s", check_err)

    logger.info("Safe database upgrade completed successfully.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Canonical safe database upgrade entrypoint.")
    parser.add_argument("--db-url", help="Database URL (optional, defaults to DATABASE_URL env)", default=None)
    args = parser.parse_args()
    code = run_safe_upgrade(args.db_url)
    sys.exit(code)


if __name__ == "__main__":
    main()
