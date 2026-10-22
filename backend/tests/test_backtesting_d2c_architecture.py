"""D2C imports only public replay/pure Risk seams and has no infrastructure effects."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "app" / "services" / "backtesting"
FILES = tuple(PACKAGE / name for name in ("risk_replay.py", "risk_replay_domain.py", "risk_replay_fingerprint.py"))
ALLOWED_RISK_MODULES = {
    "app.services.risk.domain",
    "app.services.risk.policy_core",
    "app.services.risk.policy_domain",
}
FORBIDDEN_IMPORTS = (
    "app.services.ai",
    "app.services.strategy.repository",
    "app.services.strategy.lifecycle",
    "app.models",
    "app.api",
    "sqlalchemy",
    "MetaTrader5",
    "redis",
    "httpx",
    "requests",
    "aiohttp",
    "socket",
    "uuid",
    "random",
    "pathlib",
    "os",
    "subprocess",
    "tempfile",
)
FORBIDDEN_CALLS = {
    "Session",
    "AsyncSession",
    "execute",
    "commit",
    "flush",
    "order_send",
    "now",
    "utcnow",
    "open",
    "write_text",
    "write_bytes",
    "activate",
    "reserve",
    "release",
    "create_task",
}


def test_no_live_risk_persistence_network_clock_or_execution_dependency():
    violations = []
    for path in FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module in imported:
                if module.startswith(FORBIDDEN_IMPORTS) or (
                    module.startswith("app.services.risk") and module not in ALLOWED_RISK_MODULES
                ):
                    violations.append((path.name, "import", module))
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", None))
                if name in FORBIDDEN_CALLS:
                    violations.append((path.name, "call", name))
            if isinstance(node, (ast.AsyncFunctionDef, ast.Await)):
                violations.append((path.name, "async", type(node).__name__))
    assert violations == []


def test_orchestrator_uses_public_seams_and_contains_no_later_batch_state():
    source = FILES[0].read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = [getattr(node.func, "id", None) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert names.count("make_replay_inputs") == names.count("replay") == names.count("evaluate_pure_risk") == 1
    assert not any(
        token in source
        for token in (
            "_prepare_execution",
            "RiskEngine",
            "RiskDecision",
            "PortfolioRiskManager",
            "KillSwitchManager",
            "INSERT ",
            "DELETE ",
            "UPDATE ",
            "equity_curve",
            "entry_reached",
            "tp_hit",
            "sl_hit",
            "filled",
        )
    )
