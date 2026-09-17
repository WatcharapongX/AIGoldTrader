"""Batch A.2 Remediation Tool: Pre-Upgrade 0012 Canonical Account Normalizer.

Solves finding BATCHA1-NEW-P2-001:
Safely normalizes legacy string account aliases across 0012 database tables
(paper_account_states, account_snapshots, risk_reservations) to canonical
UUIDs from the accounts table BEFORE upgrading to 0013 and 0014.

Features:
- Idempotent: detects if already >= 0013 and exits cleanly.
- Strict verification: checks for 0 matches (aborts), >1 matches across tenants (aborts).
- Conflict verification: detects true snapshot vs reservation conflicts and aborts without mutation.
- Payload synchronization: synchronizes JSON payload account_id with relational ID.
- Zero credential exposure: prints NO passwords, tokens, or confidential data.
- Supports both SQLAlchemy Connection and DBAPI / psycopg Connection.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from typing import Any

import sqlalchemy as sa

logger = logging.getLogger("normalize_0012_accounts")


class DBAdapter:
    """Adapter supporting both SQLAlchemy Connection and raw DBAPI (e.g. psycopg) Connection."""

    def __init__(self, conn: Any):
        self.raw_conn = conn
        self.is_sa = hasattr(conn, "dialect") and hasattr(conn, "connection")
        if self.is_sa:
            self.dialect = conn.dialect.name
        else:
            mod = type(conn).__module__
            self.dialect = "postgresql" if "psycopg" in mod or "postgres" in mod else "sqlite"

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        params = params or {}
        if self.is_sa:
            res = self.raw_conn.execute(sa.text(query), params)
            if res.returns_rows:
                return res.fetchall()
            return []
        else:
            if self.dialect == "postgresql":
                pyformat_query = re.sub(r":([a-zA-Z0-9_]+)", lambda m: f"%({m.group(1)})s", query)
                cur = self.raw_conn.execute(pyformat_query, params)
            else:
                cur = self.raw_conn.execute(query, params)
            try:
                return cur.fetchall()
            except Exception:
                return []

    def table_exists(self, table_name: str) -> bool:
        if self.dialect == "postgresql":
            rows = self.execute("SELECT to_regclass(:tbl)", {"tbl": table_name})
            return bool(rows and rows[0][0] is not None)
        else:
            rows = self.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = :tbl",
                {"tbl": table_name},
            )
            return bool(rows)


def normalize_0012_database(conn: Any) -> dict[str, Any]:
    """Normalizes legacy account aliases to canonical UUIDs on a 0012 database.

    Runs within the caller's connection/transaction.
    """
    db = DBAdapter(conn)

    # 1. Check current alembic revision
    if not db.table_exists("alembic_version"):
        raise RuntimeError("Cannot normalize: alembic_version table is missing (base/uninitialized revision).")

    rows = db.execute("SELECT version_num FROM alembic_version")
    if not rows:
        raise RuntimeError("Cannot normalize: alembic_version table is empty (base revision).")

    if len(rows) > 1:
        raise RuntimeError(f"Cannot normalize: multiple alembic version rows detected: {[r[0] for r in rows]}.")

    current_revision = str(rows[0][0]).strip()

    # Known later revisions: 0013, 0014, 0015 -> SKIP safely
    known_later_prefixes = ("0013", "0014", "0015")
    if any(current_revision.startswith(p) for p in known_later_prefixes):
        logger.info("Database revision is %s; skipping 0012 normalization.", current_revision)
        return {
            "status": "SKIPPED",
            "reason": f"Database already at or past revision {current_revision}",
            "normalized_aliases": 0,
        }

    # Allowed revision: strictly 0012
    if not current_revision.startswith("0012"):
        raise RuntimeError(
            f"Cannot normalize: unsupported database revision '{current_revision}'. "
            "Normalizer is strictly designed for revision 0012."
        )

    # 2. Collect all legacy string aliases across paper_account_states, account_snapshots, risk_reservations
    legacy_refs: set[str] = set()
    for tbl in ("paper_account_states", "account_snapshots", "risk_reservations"):
        if not db.table_exists(tbl):
            continue

        rows = db.execute(f"SELECT DISTINCT account_id FROM {tbl} WHERE account_id IS NOT NULL")  # noqa: S608
        for r in rows:
            ref = str(r[0])
            try:
                uuid.UUID(ref)
            except (ValueError, TypeError):
                legacy_refs.add(ref)

    if not legacy_refs:
        logger.info("No legacy account aliases found. Database is already canonical.")
        return {
            "status": "CLEAN",
            "normalized_aliases": 0,
        }

    # 3. Resolve each legacy alias against accounts table
    alias_to_uuid: dict[str, str] = {}
    for alias in legacy_refs:
        matches = db.execute(
            "SELECT id FROM accounts WHERE name = :name",
            {"name": alias},
        )
        if len(matches) == 0:
            raise RuntimeError(
                f"Pre-upgrade normalization failed: legacy account alias '{alias}' "
                f"has zero matches in accounts table; cannot guess ownership"
            )
        if len(matches) > 1:
            raise RuntimeError(
                f"Pre-upgrade normalization failed: legacy account alias '{alias}' "
                f"matches {len(matches)} accounts across tenants; ambiguous ownership"
            )
        alias_to_uuid[alias] = str(matches[0][0])

    # 4. Check for conflicting snapshot vs reservation evidence on risk_decisions
    if db.table_exists("risk_decisions"):
        evidence_rows = db.execute(
            "SELECT rd.id, s.account_id, r.account_id "
            "FROM risk_decisions rd "
            "JOIN account_snapshots s ON rd.account_snapshot_id = s.id "
            "JOIN risk_reservations r ON rd.id = r.decision_id"
        )

        conflicts: list[str] = []
        for rd_id, snap_acc, res_acc in evidence_rows:
            canon_snap = alias_to_uuid.get(str(snap_acc), str(snap_acc))
            canon_res = alias_to_uuid.get(str(res_acc), str(res_acc))
            if canon_snap != canon_res:
                conflicts.append(f"decision_id={rd_id} (snapshot={canon_snap} vs reservation={canon_res})")

        if conflicts:
            raise RuntimeError(
                f"Pre-upgrade normalization failed: conflicting canonical account evidence detected "
                f"for {len(conflicts)} RiskDecision row(s): {conflicts[:5]}"
            )

    # 5. Apply deterministic normalization updates transactionally
    for alias, canon_uuid in alias_to_uuid.items():
        # Update risk_reservations
        db.execute(
            "UPDATE risk_reservations SET account_id = :canon WHERE account_id = :alias",
            {"canon": canon_uuid, "alias": alias},
        )

        # Update account_snapshots and payload
        snap_rows = db.execute(
            "SELECT id, payload FROM account_snapshots WHERE account_id = :alias",
            {"alias": alias},
        )
        for snap_id, payload_val in snap_rows:
            updated_payload = None
            if payload_val is not None:
                p_dict = json.loads(payload_val) if isinstance(payload_val, str) else dict(payload_val)
                p_dict["account_id"] = canon_uuid
                updated_payload = json.dumps(p_dict)

            if updated_payload is not None:
                db.execute(
                    "UPDATE account_snapshots "
                    "SET account_id = :canon, payload = :payload "
                    "WHERE id = :id",
                    {"canon": canon_uuid, "payload": updated_payload, "id": snap_id},
                )
            else:
                db.execute(
                    "UPDATE account_snapshots SET account_id = :canon WHERE id = :id",
                    {"canon": canon_uuid, "id": snap_id},
                )

        # Update paper_account_states
        canon_state_exists = db.execute(
            "SELECT 1 FROM paper_account_states WHERE account_id = :canon",
            {"canon": canon_uuid},
        )

        if canon_state_exists:
            db.execute(
                "DELETE FROM paper_account_states WHERE account_id = :alias",
                {"alias": alias},
            )
        else:
            db.execute(
                "UPDATE paper_account_states SET account_id = :canon WHERE account_id = :alias",
                {"canon": canon_uuid, "alias": alias},
            )

    logger.info("Normalized %d legacy aliases to canonical UUIDs successfully.", len(alias_to_uuid))
    return {
        "status": "SUCCESS",
        "normalized_aliases": len(alias_to_uuid),
        "alias_mapping": alias_to_uuid,
    }


def main() -> int:
    """CLI entrypoint for standalone execution."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from app.core.config import get_settings

    settings = get_settings()
    engine = sa.create_engine(settings.database_url)

    logger.info("Starting pre-upgrade 0012 account normalization...")
    try:
        with engine.begin() as conn:
            result = normalize_0012_database(conn)
        logger.info("Normalization completed: %s", result["status"])
        return 0
    except Exception as exc:
        logger.error("Normalization aborted: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
