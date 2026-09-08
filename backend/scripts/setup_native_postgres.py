"""Interactive native PostgreSQL provisioning for TASK-020.

Run locally in a visible terminal. The installation password is read with getpass,
never stored. Creates new DEV/TEST databases and restricted roles only.
Existing databases, roles, authentication rules and services are never reset.
"""

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL


def connection_url(host: str, port: int, role: str, password: str, database: str) -> str:
    return URL.create(
        "postgresql+psycopg", username=role, password=password,
        host=host, port=port, database=database,
    ).render_as_string(hide_password=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["localhost", "127.0.0.1", "::1"], default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--admin-user", default="postgres")
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    env_file = backend / ".env"
    if env_file.exists():
        print("STOP: backend/.env already exists. Preserve it and review configuration before provisioning.")
        return 1

    suffix = secrets.token_hex(4)
    dev_name, test_name = f"agt_dev_{suffix}", f"agt_test_{suffix}"
    dev_password, test_password = secrets.token_urlsafe(36), secrets.token_urlsafe(36)
    pending = backend / f".env.setup-{suffix}"
    env_text = (
        "APP_ENV=DEV\nTRADING_MODE=PAPER\nLIVE_AUTO_TRADING=false\nREDIS_ENABLED=false\n"
        f"SECRET_KEY={secrets.token_urlsafe(48)}\n"
        f"DATABASE_URL={connection_url(args.host, args.port, dev_name, dev_password, dev_name)}\n"
        f"TEST_DATABASE_URL={connection_url(args.host, args.port, test_name, test_password, test_name)}\n"
        "TEST_DATABASE_DISPOSABLE=true\n"
        "CORS_ORIGINS=http://localhost:3000\n"
    )
    print("This creates NEW project DEV/TEST databases and restricted login roles.")
    print("Existing PostgreSQL data and authentication settings remain unchanged.")
    if not sys.stdin.isatty():
        print("STOP: Run this helper in an interactive terminal for hidden password entry.")
        return 1
    try:
        password = getpass.getpass("PostgreSQL installation password (hidden): ")
        conn = psycopg.connect(
            host=args.host, port=args.port, user=args.admin_user, dbname="postgres",
            password=password, connect_timeout=5, autocommit=True,
        )
        del password
    except (psycopg.Error, EOFError, KeyboardInterrupt):
        print("\nConnection not established. No database/role was created. Check the installation password.")
        return 1

    try:
        with conn:
            # Prevent setup statements containing password verifiers from entering session SQL logs.
            # These are session settings, not persistent server configuration.
            conn.execute("SET log_statement = 'none'")
            conn.execute("SET log_min_duration_statement = -1")
            with pending.open("x", encoding="utf-8") as handle:
                handle.write(env_text)
            for name, role_password in ((dev_name, dev_password), (test_name, test_password)):
                # SCRAM verifier generated client-side: plaintext password is never embedded in SQL.
                verifier = conn.pgconn.encrypt_password(
                    role_password.encode(), name.encode(), b"scram-sha-256",
                ).decode()
                conn.execute(
                    sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}")
                    .format(sql.Identifier(name), sql.Literal(verifier))
                )
                conn.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(name))
                )
                conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
            # On Windows rename fails if the destination appeared meanwhile; never overwrite it.
            os.rename(pending, env_file)
    except (psycopg.Error, OSError):
        print("Setup stopped. No existing object was reset or dropped.")
        print(f"Generated configuration, if present, is retained at {pending.name} for local recovery.")
        print("Do not share its contents. Ask for review before retrying.")
        return 1
    print(f"SUCCESS: Created {dev_name} and {test_name}.")
    print("Saved backend/.env with separate DEV/TEST credentials and a generated signing key.")
    print("The installation password was not saved. Return to Codex to continue TASK-020.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
