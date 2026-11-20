"""Batch D authorized package boundary: pure core has no live effects.

D1/D2A/D2C/D3/D4 modules are pure and infrastructure-free. The D5 runner is
the only persistence module; it may use SQLAlchemy/backtest models but must
never touch live risk execution, broker, or live order/position tables.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "app" / "services" / "backtesting"
EXPECTED_FILES = {
    "__init__.py",
    "domain.py",
    "fingerprint.py",
    "isolation.py",
    "policy.py",
    "replay.py",
    "replay_domain.py",
    "risk_replay.py",
    "risk_replay_domain.py",
    "risk_replay_fingerprint.py",
    "simulation.py",
    "simulation_domain.py",
    "metrics.py",
    "runner.py",
}
PURE_FILES = EXPECTED_FILES - {"runner.py"}
FORBIDDEN_IMPORT_PREFIXES = (
    "app.services.risk.engine",
    "app.services.risk.repository",
    "app.services.risk.kill_switch",
    "app.services.ai",
    "app.services.strategy.repository",
    "app.services.strategy.lifecycle",
    "app.api",
    "app.models",
    "sqlalchemy",
    "redis",
    "MetaTrader5",
    "httpx",
    "requests",
    "aiohttp",
    "socket",
)
FORBIDDEN_CALLS = {
    "Session",
    "AsyncSession",
    "commit",
    "flush",
    "execute",
    "order_send",
    "now",
    "utcnow",
    "open",
    "write_text",
    "write_bytes",
}
FORBIDDEN_MODULES = {"repository.py", "service.py", "engine.py", "execution.py", "api.py"}


def production_trees(names=None):
    for path in sorted(PACKAGE.glob("*.py")):
        if names is not None and path.name not in names:
            continue
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.AST) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_backtesting_package_contains_only_authorized_modules():
    names = {path.name for path in PACKAGE.glob("*.py")}
    assert names == EXPECTED_FILES
    assert not names & FORBIDDEN_MODULES


def test_pure_core_has_no_operational_or_external_imports():
    violations = []
    for path, tree in production_trees(PURE_FILES):
        for module in imported_modules(tree):
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                violations.append((path.name, module))
    assert violations == []


def test_pure_core_has_no_database_or_broker_write_calls():
    violations = []
    for path, tree in production_trees(PURE_FILES):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and call_name(node) in FORBIDDEN_CALLS:
                violations.append((path.name, call_name(node)))
    assert violations == []


def test_pure_core_defines_no_async_runner_or_sql_statements():
    violations = []
    for path, tree in production_trees(PURE_FILES):
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.Await)):
                violations.append((path.name, type(node).__name__))
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")):
                    violations.append((path.name, "SQL"))
    assert violations == []


def test_runner_touches_only_backtest_persistence():
    violations = []
    for path, tree in production_trees({"runner.py"}):
        for module in imported_modules(tree):
            if module.startswith(
                ("app.services.risk.engine", "app.services.risk.kill_switch", "app.services.ai", "MetaTrader5")
            ):
                violations.append((path.name, module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and call_name(node) == "order_send":
                violations.append((path.name, "order_send"))
    assert violations == []
