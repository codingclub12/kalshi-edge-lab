import ast
import re
from pathlib import Path

from kalshi_edge_lab import safety

SRC = Path(__file__).resolve().parents[1] / "src"
ORDER_NAME = re.compile(r"(place|create|submit|send|post)_?orders?|create_?order", re.I)


def test_constants():
    assert safety.MAX_STAKE_USD == 1
    assert safety.DRY_RUN is True


def test_only_the_read_only_client_module_exists():
    names = sorted(p.name.lower() for p in SRC.rglob("*.py") if "kalshi" in p.name.lower())
    assert names == ["kalshi_client.py"]


def test_src_has_no_order_placement():
    offenders = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if "kalshi" in mod.lower().replace("kalshi_edge_lab", "").replace(
                    "kalshi_client", ""
                ):
                    offenders.append(f"{path}: imports {mod}")
                offenders += [
                    f"{path}: imports {a.name}" for a in node.names if ORDER_NAME.search(a.name)
                ]
            elif isinstance(node, ast.Import):
                offenders += [
                    f"{path}: imports {a.name}"
                    for a in node.names
                    if "kalshi"
                    in a.name.lower().replace("kalshi_edge_lab", "").replace("kalshi_client", "")
                ]
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if ORDER_NAME.search(node.name):
                    offenders.append(f"{path}: defines {node.name}")
            elif isinstance(node, ast.Call):
                fn = node.func
                called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if ORDER_NAME.search(called):
                    offenders.append(f"{path}: calls {called}")
    assert offenders == []
