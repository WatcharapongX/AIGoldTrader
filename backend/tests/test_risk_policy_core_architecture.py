"""D2B pure-core isolation and D2B2 live-wrapper delegation gates."""

import ast
from pathlib import Path

from app.services.risk.policy_core import evaluate_pure_risk

RISK_DIR = Path(__file__).parents[1] / "app" / "services" / "risk"
PURE_FILES = (
    RISK_DIR / "policy_domain.py",
    RISK_DIR / "policy_core.py",
    RISK_DIR / "policy_fingerprint.py",
)


def _imports_and_calls(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.add(node.func.id)
    return imports, calls


def test_pure_production_files_have_no_forbidden_dependencies_or_effects():
    forbidden_import_fragments = {
        "sqlalchemy",
        "app.models",
        "risk.repository",
        "risk.kill_switch",
        "risk.portfolio",
        "app.services.backtesting",
        "MetaTrader5",
        "httpx",
        "requests",
        "aiohttp",
        "socket",
        "subprocess",
        "fastapi",
        "provider",
    }
    forbidden_calls = {
        "now",
        "utcnow",
        "time",
        "uuid4",
        "open",
        "write_text",
        "write_bytes",
        "activate",
        "check",
        "get_state",
        "evaluate_automatic_triggers",
    }
    for path in PURE_FILES:
        imports, calls = _imports_and_calls(path)
        assert not {
            imported
            for imported in imports
            if any(fragment.lower() in imported.lower() for fragment in forbidden_import_fragments)
        }
        assert not (calls & forbidden_calls)


def test_live_wrapper_delegates_policy_without_reimplementing_sizing_or_capacity():
    engine_source = (RISK_DIR / "engine.py").read_text(encoding="utf-8")
    assert "evaluate_pure_risk" in engine_source
    assert "PureRiskResult" in engine_source
    assert "calculate_position_size" not in engine_source
    assert "check_budget_capacity" not in engine_source
    assert callable(evaluate_pure_risk)
