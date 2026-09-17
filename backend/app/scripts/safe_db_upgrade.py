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
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from app.scripts.normalize_0012_accounts import normalize_0012_database

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


def get_current_revision(conn: psycopg.Connection) -> str | None:
    """Queries alembic_version table to determine current revision."""
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
        return str(rows[0][0]).strip()


def run_safe_upgrade(db_url: str | None = None) -> int:
    """Executes the safe upgrade workflow."""
    if not db_url:
        backend_dir = Path(__file__).resolve().parents[2]
        env_config = dotenv_values(backend_dir / ".env")
        db_url = os.environ.get("DATABASE_URL") or env_config.get("DATABASE_URL")

    if not db_url:
        logger.error("DATABASE_URL is not set and could not be discovered from .env")
        return 1

    masked = mask_url(db_url)
    logger.info("Starting safe database upgrade against %s", masked)

    url_obj = make_url(db_url)
    driver_less = url_obj.set(drivername="postgresql").render_as_string(hide_password=False)

    try:
        with psycopg.connect(driver_less, autocommit=False) as conn:
            current_rev = get_current_revision(conn)
            logger.info("Current revision: %s", current_rev or "None (uninitialized)")

            normalizer_required = False
            if current_rev is None:
                logger.error("Cannot upgrade: database has no alembic_version table. Run alembic stamp/init first.")
                return 1

            if current_rev.startswith("0012"):
                normalizer_required = True
                logger.info("Normalizer required: YES (revision %s detected)", current_rev)
            elif any(current_rev.startswith(p) for p in ("0013", "0014", "0015")):
                normalizer_required = False
                logger.info("Normalizer required: NO (database already at or past %s)", current_rev)
            else:
                logger.error(
                    "Unsupported database revision '%s'. Normalizer supports 0012, skips >=0013. Failing closed.",
                    current_rev,
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

    env = {**os.environ, "DATABASE_URL": db_url}
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
