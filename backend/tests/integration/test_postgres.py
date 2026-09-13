"""Opt-in PostgreSQL gate; never uses DATABASE_URL for integration test selection.

Set TEST_DATABASE_URL and TEST_DATABASE_DISPOSABLE=true. A unique owned schema
isolates migration up/down/up; no existing schema/table is dropped.
"""

import asyncio
import datetime as dt
import os
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.core.event_loop import new_event_loop
from app.core.security import verify_password
from app.db.seed import seed_admin
from app.db.session import get_session_factory
from app.main import create_app
from app.models import AuditLog, RefreshSession, Role, User

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_postgres(monkeypatch):
    local_config = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
    raw_url = os.environ.get("TEST_DATABASE_URL", local_config.get("TEST_DATABASE_URL"))
    if not raw_url:
        pytest.skip("BLOCKED BY LOCAL POSTGRESQL: TEST_DATABASE_URL is not configured")
    disposable = os.environ.get("TEST_DATABASE_DISPOSABLE", local_config.get("TEST_DATABASE_DISPOSABLE"))
    if disposable != "true":
        pytest.skip("Set TEST_DATABASE_DISPOSABLE=true only for a disposable test database")

    monkeypatch.delenv("DATABASE_URL_OVERRIDE", raising=False)
    monkeypatch.setenv("DATABASE_URL", raw_url)
    get_settings.cache_clear()
    url = make_url(Settings(_env_file=None).database_url)
    assert url.get_backend_name() == "postgresql", "Integration gate requires real PostgreSQL"
    dev_url = local_config.get("DATABASE_URL")
    if dev_url:
        dev = make_url(dev_url)
        assert (url.host, url.port, url.database) != (dev.host, dev.port, dev.database), (
            "TEST_DATABASE_URL must target a separate database from DEV"
        )
    connection_url = url.set(drivername="postgresql").render_as_string(hide_password=False)
    # The caller supplied a test DB. Only this newly created schema is modified.
    schema = "phase1_gate_" + uuid.uuid4().hex
    with psycopg.connect(connection_url, autocommit=True, connect_timeout=5) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            isolated = url.update_query_dict({"options": f"-csearch_path={schema}"})
            monkeypatch.setenv("DATABASE_URL", isolated.render_as_string(hide_password=False))
            get_settings.cache_clear()
            yield conn, schema
        finally:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            get_settings.cache_clear()


def _alembic(*args, success=True):
    result = subprocess.run(  # noqa: S603 — fixed commands, owned TEST schema
        [sys.executable, "-m", "alembic", *args],
        cwd=Path(__file__).resolve().parents[2],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    log = result.stdout + result.stderr
    url = make_url(os.environ["DATABASE_URL"])
    sensitive = (url.password, os.environ["DATABASE_URL"], get_settings().secret_key)
    if any(value and value in log for value in sensitive):
        pytest.fail("Sensitive data appeared in Alembic output", pytrace=False)
    # Never expose driver errors containing credentials or URL values.
    assert (result.returncode == 0) is success, "Unexpected Alembic result in isolated TEST schema"
    if args == ("check",):
        if success:
            assert "No new upgrade operations detected" in result.stdout
        else:
            assert "New upgrade operations detected" in result.stdout + result.stderr


def test_postgresql_migrations_auth_and_audit(isolated_postgres, capfd):
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    expected = {
        "users",
        "sessions",
        "accounts",
        "symbols",
        "audit_logs",
        "system_events",
        "ticks",
        "candles",
        "economic_events",
        "economic_event_revisions",
        "trader_profiles",
        "strategy_evaluations",
        "trade_candidates",
        "candidate_transitions",
        "risk_policies",
        "symbol_specifications",
        "account_snapshots",
        "risk_decisions",
        "risk_reservations",
        "kill_switch_records",
        "data_health_records",
        "paper_account_states",
    }
    for action, target in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
        if target == "base":
            # Sol High P1-032: Downgrade refuses when authority rows exist. Explicit purge outside downgrade required.
            for t in (
                "paper_account_states",
                "data_health_records",
                "risk_decisions",
                "risk_reservations",
                "kill_switch_records",
                "account_snapshots",
                "symbol_specifications",
                "risk_policies",
            ):
                conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(t)))
        _alembic(action, target)
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            (schema,),
        ).fetchall()
        actual = {row[0] for row in rows} - {"alembic_version"}
        assert actual == (set() if target == "base" else expected)
        if target == "head":
            _verify_schema(conn, schema, expected)
            _verify_json_columns(conn, schema, "jsonb")
            _alembic("check")
            sensitive = asyncio.run(_verify_auth(), loop_factory=new_event_loop)
            captured = capfd.readouterr()
            if any(value in captured.out + captured.err for value in sensitive):
                pytest.fail("Sensitive authentication data appeared in captured logs", pytrace=False)
        else:
            revision = conn.execute(
                sql.SQL("SELECT version_num FROM {}.alembic_version").format(sql.Identifier(schema))
            ).fetchall()
            assert revision == []


def _verify_json_columns(conn, schema, data_type):
    expected = {
        ("audit_logs", "before"): "YES",
        ("audit_logs", "after"): "YES",
        ("symbols", "session_hours"): "NO",
        ("system_events", "payload"): "YES",
    }
    for (table, column), nullable in expected.items():
        actual = conn.execute(
            "SELECT data_type,is_nullable,column_default FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s AND column_name=%s",
            (schema, table, column),
        ).fetchone()
        default = f"'{{}}'::{data_type}" if table == "symbols" else None
        assert actual == (data_type, nullable, default)


def test_postgresql_corrective_roundtrip_and_drift_gate(isolated_postgres):
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "0001_initial")
    _verify_json_columns(conn, schema, "json")
    # Real pre-existing JSON in all four columns, including SQL NULL vs JSON null.
    payloads = [
        '{"nested":{"thai":"ทอง","items":[1,true,null,{"value":1.25}]},"empty":{}}',
        "{}",
        "null",
        None,
    ]
    for index, payload in enumerate(payloads):
        conn.execute(
            'INSERT INTO audit_logs (id,action,entity,"before","after") VALUES (%s,%s,%s,%s,%s)',
            (uuid.uuid4(), "MIGRATION_TEST", "test", payload, payload),
        )
        conn.execute(
            "INSERT INTO system_events (id,category,severity,code,message,payload,correlation_id) "
            "VALUES (%s,'DB','INFO','MIGRATION_TEST','test',%s,'migration-test')",
            (uuid.uuid4(), payload),
        )
        if payload is not None:
            conn.execute(
                "INSERT INTO symbols (id,name,session_hours) VALUES (%s,%s,%s)",
                (uuid.uuid4(), f"TEST{index}", payload),
            )
    conn.execute("INSERT INTO symbols (id,name) VALUES (%s,'DEFAULT')", (uuid.uuid4(),))
    user_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO users (id,email,password_hash,role) VALUES (%s,'migration@example.com','fixture','VIEWER')",
        (user_id,),
    )
    session_hash = "migration-fixture-hash"
    conn.execute(
        "INSERT INTO sessions (id,user_id,refresh_token_hash,expires_at) VALUES (%s,%s,%s,now())",
        (uuid.uuid4(), user_id, session_hash),
    )

    def snapshot():
        return {
            table: conn.execute(
                sql.SQL("SELECT to_jsonb(t) - 'default_spread' FROM {} t ORDER BY id").format(sql.Identifier(table))
            ).fetchall()
            for table in ("users", "sessions", "symbols", "audit_logs", "system_events")
        }

    before = snapshot()
    for action, target, data_type in (
        ("upgrade", "head", "jsonb"),
        ("downgrade", "0001_initial", "json"),
        ("upgrade", "head", "jsonb"),
    ):
        if target == "0001_initial":
            # Sol High P1-032: Downgrade refuses when authority rows exist. Explicit purge outside downgrade required.
            for t in (
                "paper_account_states",
                "data_health_records",
                "risk_decisions",
                "risk_reservations",
                "kill_switch_records",
                "account_snapshots",
                "symbol_specifications",
                "risk_policies",
            ):
                conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(t)))
        _alembic(action, target)
        _verify_json_columns(conn, schema, data_type)
        assert snapshot() == before
        assert conn.execute(
            'SELECT count(*) FILTER (WHERE "before" IS NULL), '
            'count(*) FILTER (WHERE "before"::text = %s) FROM audit_logs',
            ("null",),
        ).fetchone() == (1, 1)
        assert conn.execute("SELECT session_hours FROM symbols WHERE name='DEFAULT'").fetchone() == ({},)
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                "INSERT INTO sessions (id,user_id,refresh_token_hash,expires_at) VALUES (%s,%s,%s,now())",
                (uuid.uuid4(), user_id, session_hash),
            )
        if target == "head":
            _alembic("check")
        else:
            assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0001_initial",)

    # Prove the gate actually detects both original defect classes at HEAD.
    conn.execute('ALTER TABLE audit_logs ALTER COLUMN "before" TYPE json USING "before"::json')
    _alembic("check", success=False)
    conn.execute('ALTER TABLE audit_logs ALTER COLUMN "before" TYPE jsonb USING "before"::jsonb')
    _alembic("check")
    conn.execute("DROP INDEX ix_sessions_refresh_token_hash")
    conn.execute("ALTER TABLE sessions ADD CONSTRAINT uq_sessions_refresh_token_hash UNIQUE (refresh_token_hash)")
    _alembic("check", success=False)
    conn.execute("ALTER TABLE sessions DROP CONSTRAINT uq_sessions_refresh_token_hash")
    conn.execute("CREATE UNIQUE INDEX ix_sessions_refresh_token_hash ON sessions (refresh_token_hash)")
    _alembic("check")
    assert snapshot() == before


def _verify_schema(conn, schema, expected):
    revision = conn.execute(
        sql.SQL("SELECT version_num FROM {}.alembic_version").format(sql.Identifier(schema))
    ).fetchone()
    assert revision in (("0011_phase5_final_acceptance",), ("0012_phase5_reconciliation",))
    indexes = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s", (schema,)
        ).fetchall()
    }
    for unique_index in ("ix_users_email", "ix_sessions_refresh_token_hash", "ix_symbols_name"):
        assert "UNIQUE INDEX" in indexes[unique_index]
    assert "uq_sessions_refresh_token_hash" not in indexes
    assert {"ix_accounts_user_id", "ix_sessions_user_id", "ix_audit_logs_ts", "ix_audit_logs_action"} <= indexes.keys()
    constraints = conn.execute(
        "SELECT table_name, constraint_type FROM information_schema.table_constraints WHERE table_schema = %s",
        (schema,),
    ).fetchall()
    assert {table for table, kind in constraints if kind == "PRIMARY KEY"} == expected | {"alembic_version"}
    foreign_tables = {table for table, kind in constraints if kind == "FOREIGN KEY"}
    assert foreign_tables == {
        "sessions",
        "accounts",
        "ticks",
        "candles",
        "economic_event_revisions",
        "trade_candidates",
        "candidate_transitions",
        "risk_reservations",
    }


async def _verify_auth():
    app = create_app()
    async with app.router.lifespan_context(app):
        password = secrets.token_urlsafe(32)
        await seed_admin("phase1@example.com", password)
        factory = get_session_factory()
        async with factory() as session:
            user = (await session.execute(select(User).where(User.email == "phase1@example.com"))).scalar_one()
            user_id = user.id
            assert user.password_hash != password
            assert verify_password(password, user.password_hash)
            password_hash = user.password_hash

        # Actual PostgreSQL transaction rollback, unique index and FK enforcement.
        async with factory() as session:
            session.add(User(email="rollback@example.com", password_hash=password_hash, role=Role.VIEWER))
            await session.flush()
            await session.rollback()
        async with factory() as session:
            rolled_back = await session.execute(select(User).where(User.email == "rollback@example.com"))
            assert rolled_back.scalar_one_or_none() is None
            session.add(User(email="phase1@example.com", password_hash=password_hash, role=Role.VIEWER))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
            session.add(
                RefreshSession(
                    user_id=uuid.uuid4(),
                    refresh_token_hash=secrets.token_hex(32),
                    expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/healthz")
            assert health.json()["trading_mode"] == "PAPER"
            assert health.json()["live_auto_trading"] is False
            ready = await client.get("/readyz")
            assert ready.status_code == 200
            assert ready.json()["checks"] == {"database": True, "redis": None}
            wrong = await client.post(
                "/api/auth/login",
                json={
                    "email": "phase1@example.com",
                    "password": "incorrect-test-password",
                },
            )
            unknown = await client.post(
                "/api/auth/login",
                json={
                    "email": "unknown@example.com",
                    "password": "incorrect-test-password",
                },
            )
            assert wrong.status_code == unknown.status_code == 401
            assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
            assert password not in wrong.text + unknown.text
            login = await client.post("/api/auth/login", json={"email": "phase1@example.com", "password": password})
            assert login.status_code == 200
            tokens = login.json()
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            assert (await client.get("/api/auth/me", headers=headers)).json()["role"] == "ADMIN"
            refreshed = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            assert refreshed.status_code == 200
            replay = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            assert replay.status_code == 401
            assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200
            replay = await client.post("/api/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]})
            assert replay.status_code == 401
        async with get_session_factory()() as session:
            audits = (await session.execute(select(AuditLog).where(AuditLog.action == "LOGIN"))).scalars().all()
            assert len(audits) == 1
            assert audits[0].user_id == user_id
            assert audits[0].entity_id == str(user_id)
            assert audits[0].entity == "user" and audits[0].source == "API"
            assert audits[0].ts.tzinfo is not None
            assert audits[0].correlation_id and audits[0].correlation_id != "-"
            assert audits[0].after == {"email": "phase1@example.com", "role": "ADMIN"}
            user = await session.get(User, user_id)
            assert user is not None and user.last_login_at is not None
            sessions = (
                (await session.execute(select(RefreshSession).where(RefreshSession.user_id == user_id))).scalars().all()
            )
            assert len(sessions) == 2 and all(item.revoked_at for item in sessions)
            assert all(item.refresh_token_hash != tokens["refresh_token"] for item in sessions)
        return (password, tokens["access_token"], tokens["refresh_token"], get_settings().secret_key)


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_postgresql_hardening_correlation_and_exception_logs(isolated_postgres, monkeypatch, capfd, log_format):
    monkeypatch.setenv("LOG_FORMAT", log_format)
    get_settings.cache_clear()
    conn, schema = isolated_postgres
    _alembic("upgrade", "head")
    from app.api import auth
    from app.core.rate_limit import RateLimiter

    monkeypatch.setattr(auth, "_auth_limiter", RateLimiter(100))
    sensitive = asyncio.run(_verify_hardening(), loop_factory=new_event_loop)
    captured = capfd.readouterr()
    assert not any(value in captured.out + captured.err for value in sensitive)
    assert "DataError" in captured.out
    assert "db-error-123" in captured.out
    assert "http_request" in captured.out
    _alembic("check")


async def _verify_hardening():
    from sqlalchemy import text

    from app.db.session import get_engine
    from app.services.audit import write_audit

    app = create_app()
    parameter = secrets.token_urlsafe(32)

    @app.get("/_gate/database-error")
    async def database_error():
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT CAST(:credential AS INTEGER)"), {"credential": parameter})

    password = secrets.token_urlsafe(32)
    async with app.router.lifespan_context(app):
        await seed_admin("hardening@example.com", password)
        assert get_engine().sync_engine.hide_parameters is True
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            for incoming in ("v" * 64, "x" * 65, "invalid space", "bad\nforged", "bad\rforged"):
                response = await client.post(
                    "/api/auth/login",
                    headers={"X-Correlation-ID": incoming},
                    json={
                        "email": "hardening@example.com",
                        "password": password,
                    },
                )
                assert response.status_code == 200
                correlation = response.headers["X-Correlation-ID"]
                assert len(correlation) <= 64
                assert (correlation == incoming) is (len(incoming) == 64)
                async with get_session_factory()() as session:
                    entry = (
                        await session.execute(
                            select(AuditLog).where(
                                AuditLog.action == "LOGIN",
                                AuditLog.correlation_id == correlation,
                            )
                        )
                    ).scalar_one()
                    assert entry.after == {"email": "hardening@example.com", "role": "ADMIN"}
            failed = await client.get("/_gate/database-error", headers={"X-Correlation-ID": "db-error-123"})
            assert failed.status_code == 500
            assert failed.headers["X-Correlation-ID"] == "db-error-123"
            assert parameter not in failed.text
        async with get_session_factory()() as session:
            entry = await write_audit(
                session,
                action="CORRELATION_TEST",
                entity="test",
                correlation_id="x" * 65,
            )
            await session.commit()
            assert len(entry.correlation_id) <= 64
    return parameter, password, get_settings().secret_key


@pytest.mark.parametrize(
    "surface",
    [
        "README.md",
        "docs/18-devops.md",
        "backend/Dockerfile",
        "docker-compose.yml",
        "docker-compose.dev.yml",
    ],
)
def test_live_launch_surfaces_preserve_peer(isolated_postgres, tmp_path, surface):
    from launch_support import launch_commands, native_server

    _alembic("upgrade", "head")
    conn, schema = isolated_postgres
    command = launch_commands()[surface]
    assert "--no-proxy-headers" in command
    log = tmp_path / "server.log"
    with native_server(
        command,
        log,
        extra_env={
            "TRUST_PROXY": "false",
            "RATE_LIMIT_AUTH_PER_MINUTE": "3",
            "FORWARDED_ALLOW_IPS": "*",
        },
    ) as client:
        statuses = []
        for index in range(4):
            response = client.post(
                "/api/auth/login",
                headers={
                    "X-Forwarded-For": f"203.0.113.{index + 1}",
                    "X-Real-IP": f"192.0.2.{index + 1}",
                    "Forwarded": f"for=198.51.100.{index + 1}",
                },
                json={"email": f"launch{index}@example.com", "password": "incorrect-password"},
            )
            statuses.append(response.status_code)
        assert statuses == [401, 401, 401, 429]
        correlation = response.headers["X-Correlation-ID"]
    actual = conn.execute(
        sql.SQL("SELECT ip FROM {}.audit_logs WHERE action='LOGIN_RATE_LIMITED' AND correlation_id=%s").format(
            sql.Identifier(schema)
        ),
        (correlation,),
    ).fetchone()
    assert actual == ("127.0.0.1",)


@pytest.mark.parametrize(
    ("trusted", "expected_ip", "expected_statuses"),
    [
        ("127.0.0.1/32", "203.0.113.4", [401, 401, 401, 401]),
        ("192.0.2.0/24", "127.0.0.1", [401, 401, 401, 429]),
    ],
)
def test_live_base_compose_proxy_opt_in(isolated_postgres, tmp_path, trusted, expected_ip, expected_statuses):
    from launch_support import launch_commands, native_server

    _alembic("upgrade", "head")
    # Probe the exact same production resolver, without modifying its reviewed implementation.
    module = tmp_path / "peer_probe.py"
    module.write_text(
        "from fastapi import Request\nfrom app.main import create_app\n"
        "from app.core.client_ip import resolve_client_ip\napp=create_app()\n"
        "@app.get('/_gate/peer')\nasync def peer(request: Request):\n"
        "    return {'ip': resolve_client_ip(request)}\n",
        encoding="utf-8",
    )
    with native_server(
        launch_commands()["docker-compose.yml"],
        tmp_path / "proxy.log",
        extra_env={
            "TRUST_PROXY": "true",
            "TRUSTED_PROXY_CIDRS": trusted,
            "RATE_LIMIT_AUTH_PER_MINUTE": "3",
            "PYTHONPATH": str(tmp_path),
            "FORWARDED_ALLOW_IPS": "*",
        },
        app_module="peer_probe:app",
    ) as client:
        statuses = [
            client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": f"203.0.113.{index + 1}"},
                json={"email": f"proxy{index}@example.com", "password": "incorrect-password"},
            ).status_code
            for index in range(4)
        ]
        assert statuses == expected_statuses
        assert client.get("/_gate/peer", headers={"X-Forwarded-For": "203.0.113.4"}).json() == {"ip": expected_ip}
        assert client.get("/_gate/peer", headers={"X-Forwarded-For": "invalid-chain"}).json() == {"ip": "127.0.0.1"}


def test_live_correlation_response_audit_access_and_concurrency(isolated_postgres, tmp_path):
    import json
    from concurrent.futures import ThreadPoolExecutor

    from launch_support import launch_commands, log_records, native_server

    _alembic("upgrade", "head")
    conn, schema = isolated_postgres
    module = tmp_path / "correlation_probe.py"
    module.write_text(
        "import asyncio\nfrom fastapi import Depends\n"
        "from app.main import create_app\nfrom app.db.session import get_session\n"
        "from app.core.correlation import get_correlation_id\nfrom app.services.audit import write_audit\n"
        "app=create_app()\n@app.get('/_gate/audit/{label}')\n"
        "async def probe(label: str, session=Depends(get_session)):\n"
        "    await asyncio.sleep(0.02)\n"
        "    await write_audit(session, action='CORRELATION_PROBE', entity='test', entity_id=label)\n"
        "    await session.commit()\n"
        "    if label == 'failure': raise ValueError('fixture-sensitive-body')\n"
        "    return {'correlation_id': get_correlation_id()}\n",
        encoding="utf-8",
    )
    log = tmp_path / "correlation.log"
    with native_server(
        launch_commands()["docker-compose.yml"],
        log,
        extra_env={
            "PYTHONPATH": str(tmp_path),
            "LOG_FORMAT": "json",
        },
        app_module="correlation_probe:app",
    ) as client:
        expected = {}
        for label, incoming in (("valid", "valid-123"), ("invalid", "x" * 65), ("failure", "failure-123")):
            response = client.get("/_gate/audit/" + label, headers={"X-Correlation-ID": incoming})
            assert response.status_code == (500 if label == "failure" else 200)
            canonical = response.headers["X-Correlation-ID"]
            assert canonical == incoming if label != "invalid" else canonical != incoming
            body = response.json()
            body_id = body["error"]["correlation_id"] if label == "failure" else body["correlation_id"]
            assert body_id == canonical
            expected[label] = canonical

        def probe(index):
            label, correlation = f"parallel-{index}", f"concurrent-{index}"
            response = client.get("/_gate/audit/" + label, headers={"X-Correlation-ID": correlation})
            assert response.status_code == 200
            assert response.headers["X-Correlation-ID"] == response.json()["correlation_id"] == correlation
            return label, correlation

        with ThreadPoolExecutor(max_workers=6) as pool:
            expected.update(pool.map(probe, range(12)))
    records = log_records(log)
    accesses = [row for row in records if row.get("logger") == "uvicorn.access"]
    for label, canonical in expected.items():
        matches = [row for row in accesses if f"/_gate/audit/{label} HTTP/" in row["message"]]
        assert len(matches) == 1 and matches[0]["correlation_id"] == canonical
        audit_id = conn.execute(
            sql.SQL("SELECT correlation_id FROM {}.audit_logs WHERE entity_id=%s").format(sql.Identifier(schema)),
            (label,),
        ).fetchone()
        assert audit_id == (canonical,)
        app_logs = [
            row for row in records if row.get("audit_action") == "CORRELATION_PROBE" and row.get("entity_id") == label
        ]
        assert len(app_logs) == 1 and app_logs[0]["correlation_id"] == canonical
    errors = [row for row in records if row.get("error_type") == "ValueError"]
    assert len(errors) == 1 and errors[0]["correlation_id"] == expected["failure"]
    assert all(row["correlation_id"] != "-" for row in accesses)
    rendered = json.dumps(records)
    assert "fixture-sensitive-body" not in rendered
    assert os.environ["DATABASE_URL"] not in rendered and get_settings().secret_key not in rendered
    _alembic("check")
