"""W14-D8 (TASK-0097): PowerShell variable names ignore case.

A local variable that differs from a parameter only in case is the same variable, so assigning
it silently replaces the parameter. Submit-ExecRequest once did this with ``$requestId`` and
``$RequestId``: every Windows job ran under a new random request ID, and setup waited for an ID
that never came. This guard fails on any such assignment in the installer's product scripts.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "infra/windows/installer/scripts"
ASSIGN = re.compile(r"\$(\w+)\s*(?:=(?!=)|\+=|-=)|foreach\s*\(\s*\$(\w+)\s+in\b", re.IGNORECASE)


def param_names(chunk: str) -> tuple[list[str], int]:
    """The names of the first param block in ``chunk`` (not those of nested script blocks)."""
    match = re.search(r"(?i)\bparam\s*\(", chunk)
    if match is None:
        return [], 0
    index, depth, brace, names = match.end(), 1, 0, []
    while index < len(chunk) and depth:
        char = chunk[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "{":
            brace += 1
        elif char == "}":
            brace -= 1
        elif char == "$" and brace == 0 and depth == 1:
            name = re.match(r"\$(\w+)", chunk[index:])
            if name:
                names.append(name.group(1))
        index += 1
    return names, index


def clashes(text: str) -> list[str]:
    """Each assignment to a name that matches a parameter of its function or script only in case."""
    starts = [match.start() for match in re.finditer(r"(?m)^function\s", text)] + [len(text)]
    chunks = [(0, text[: starts[0]])]
    chunks += [(starts[k], text[starts[k] : starts[k + 1]]) for k in range(len(starts) - 1)]
    found = []
    for offset, chunk in chunks:
        names, end = param_names(chunk)
        lower = {name.lower(): name for name in names}
        for match in ASSIGN.finditer(chunk, end):
            name = match.group(1) or match.group(2)
            if name.lower() in lower and name != lower[name.lower()]:
                line = text[: offset + match.start()].count("\n") + 1
                found.append(f"line {line}: ${name} is the parameter ${lower[name.lower()]}")
    return found


class PowerShellNameCaseTest(unittest.TestCase):
    def test_w14_d8_no_assignment_replaces_a_parameter_by_case(self) -> None:
        scripts = sorted(SCRIPTS.rglob("*.ps1"))
        self.assertTrue(scripts)
        for script in scripts:
            with self.subTest(script=str(script.relative_to(ROOT))):
                self.assertEqual([], clashes(script.read_text(encoding="utf-8-sig")))

    def test_the_guard_finds_the_submit_exec_request_clash(self) -> None:
        text = (
            "function Submit-ExecRequest {\n    param([string]$RequestId = '')\n"
            "    $requestId = [guid]::NewGuid().ToString('D')\n    return $requestId\n}\n"
        )
        self.assertEqual(["line 3: $requestId is the parameter $RequestId"], clashes(text))

    def test_a_nested_script_block_parameter_is_not_the_function_parameter(self) -> None:
        text = (
            "function Remove-SetupData {\n    param(\n        [scriptblock]$ExecJob = {\n"
            "            param([string]$Job)\n        }\n    )\n    $job = & $ExecJob 'x'\n}\n"
        )
        self.assertEqual([], clashes(text))


if __name__ == "__main__":
    unittest.main()
