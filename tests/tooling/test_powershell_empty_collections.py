"""AC-O7 (TASK-0097, owner rc.28): a Mandatory collection parameter refuses an empty collection.

Windows PowerShell binds an empty array or list to a ``Mandatory`` parameter of an array or
collection type only with ``[AllowEmptyCollection()]``; otherwise the call fails with "Cannot
bind argument to parameter ... because it is an empty collection". Save report failed this way
in rc.28 (``Add-ReportFile -LeftOut`` with nothing left out yet), and a zero-length UDP packet
ended the mDNS responder the same way. This guard fails on every such parameter in the
installer's product scripts unless it allows an empty collection or is listed below with the
reason it is never empty.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "infra/windows/installer/scripts"
MANDATORY = re.compile(r"\[Parameter\(Mandatory\s*=\s*\$true\)\]", re.IGNORECASE)
COLLECTION = re.compile(r"(\[\]$|\b(List|HashSet|Collection|IList|ICollection|ArrayList)\b)")
# (script, function, parameter): why the value is never empty.
NEVER_EMPTY = {
    ("lib/Exec.ps1", "Invoke-ProcessWithInput", "ArgumentList"): (
        "Get-EngineArguments always gives the seven fixed arguments of an engine job"
    ),
    ("lib/Exec.ps1", "Write-ReceiveStream", "RequestBytes"): (
        "Test-ReceiveInput has checked the receive input as a JSON object before the writer runs"
    ),
    ("lib/Windows.ps1", "Copy-PayloadPart", "Names"): (
        "the callers pass the fixed list of payload part names"
    ),
}


def bracket_groups(text: str, index: int) -> tuple[list[str], int]:
    """The bracketed groups that follow ``index`` back to back, with nested brackets kept."""
    groups = []
    while index < len(text) and text[index] == "[":
        depth, start = 0, index
        while index < len(text):
            if text[index] == "[":
                depth += 1
            elif text[index] == "]":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        groups.append(text[start + 1 : index])
        index += 1
    return groups, index


def refusing_parameters(text: str) -> list[tuple[str, str, str]]:
    """(function, parameter, type) of each Mandatory collection parameter without the allowance."""
    found = []
    for match in MANDATORY.finditer(text):
        groups, end = bracket_groups(text, match.end())
        name = re.match(r"\s*\$(\w+)", text[end:])
        if not groups or name is None:
            continue
        attributes, kind = groups[:-1], groups[-1]
        if not COLLECTION.search(kind) or "AllowEmptyCollection()" in attributes:
            continue
        functions = re.findall(r"(?m)^function\s+([\w-]+)", text[: match.start()])
        found.append((functions[-1] if functions else "", name.group(1), kind))
    return found


class EmptyCollectionGuardTest(unittest.TestCase):
    def test_ac_o7_the_guard_finds_a_mandatory_collection_without_the_allowance(self) -> None:
        sample = (
            "function Add-One {\n    param([Parameter(Mandatory = $true)]"
            "[System.Collections.Generic.List[string]]$LeftOut, [string[]]$Names)\n}\n"
            "function Add-Two {\n    param([Parameter(Mandatory = $true)][AllowEmptyCollection()]"
            "[byte[]]$Data, [Parameter(Mandatory = $true)][string]$Name)\n}\n"
        )
        self.assertEqual(
            refusing_parameters(sample),
            [("Add-One", "LeftOut", "System.Collections.Generic.List[string]")],
        )

    def test_ac_o7_no_product_script_refuses_an_empty_collection(self) -> None:
        problems = []
        for path in sorted(SCRIPTS.rglob("*.ps1")):
            script = path.relative_to(SCRIPTS).as_posix()
            for function, parameter, kind in refusing_parameters(path.read_text(encoding="ascii")):
                if (script, function, parameter) not in NEVER_EMPTY:
                    problems.append(f"{script} {function} -{parameter} [{kind}]")
        self.assertEqual(problems, [])

    def test_ac_o7_every_never_empty_entry_still_exists(self) -> None:
        for script, function, parameter in NEVER_EMPTY:
            with self.subTest(parameter=f"{script} {function} -{parameter}"):
                text = (SCRIPTS / script).read_text(encoding="ascii")
                self.assertIn(
                    (function, parameter),
                    [(found[0], found[1]) for found in refusing_parameters(text)],
                )


if __name__ == "__main__":
    unittest.main()
