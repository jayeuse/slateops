"""Only the provider sign-out rule reads Auth's error code (contract 5.2 item 4, C11, S1).

`InvalidProviderCredentials.error_code` carries Auth's exact code. A route, log or security event
that read it could tell a caller why Auth refused, so the one allowed reader is the completion
rule in `provider_signout.py`. Setting the attribute is a store, not a read.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
ALLOWED_READERS = {"systems/access/identity/provider_signout.py"}


def _reads_error_code(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "error_code"
            and isinstance(node.ctx, ast.Load)
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "hasattr"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "error_code"
        ):
            return True
    return False


def test_only_the_signout_rule_reads_auths_error_code_s1() -> None:
    readers = {
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if _reads_error_code(ast.parse(path.read_text(encoding="utf-8")))
    }

    assert readers == ALLOWED_READERS
