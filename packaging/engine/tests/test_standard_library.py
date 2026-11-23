"""W5b-5: the engine on the Linux host uses only the Python standard library."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]


def _import_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_w5b_5_every_engine_module_imports_only_the_standard_library() -> None:
    sources = [p for p in ENGINE.rglob("*.py") if "tests" not in p.relative_to(ENGINE).parts]
    sources.append(ENGINE / "slateops-engine")

    outside = {
        f"{path.name}: {root}"
        for path in sources
        for root in _import_roots(path)
        if root not in sys.stdlib_module_names and root not in ("engine", "__future__")
    }

    assert len(sources) > 20
    assert outside == set()
