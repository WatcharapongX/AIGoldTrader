"""D2A production isolation proof by imports, calls, syntax, and semantic vocabulary."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "app" / "services" / "backtesting"
FILES = (PACKAGE / "replay.py", PACKAGE / "replay_domain.py")
FORBIDDEN_IMPORTS = (
    "app.services.risk",
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
FORBIDDEN_WORDS = {
    "RiskDecision",
    "RiskEngine",
    "KillSwitch",
    "entry_reached",
    "filled",
    "tp_hit",
    "sl_hit",
    "profit_factor",
    "equity_curve",
}


def modules(tree):
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def call_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_d2a_has_no_live_external_persistence_or_execution_dependency():
    violations = []
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for module in modules(tree):
            if module.startswith(FORBIDDEN_IMPORTS):
                violations.append((path.name, "import", module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and call_name(node) in FORBIDDEN_CALLS:
                violations.append((path.name, "call", call_name(node)))
            if isinstance(node, (ast.AsyncFunctionDef, ast.Await)):
                violations.append((path.name, "async", type(node).__name__))
        for word in FORBIDDEN_WORDS:
            if word in source:
                violations.append((path.name, "semantic", word))
    assert violations == []


def test_d2a_files_are_the_only_new_operational_layer_and_contain_no_sql_or_paths():
    assert {path.name for path in FILES} == {"replay.py", "replay_domain.py"}
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        assert not any(token in source.upper() for token in ("INSERT ", "UPDATE ", "DELETE "))
        assert "Path(" not in source and "filesystem" not in source.lower()
