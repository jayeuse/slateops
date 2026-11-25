"""The update proof in ``packaging/linux-image/install-proof.sh`` makes two test-only versions
from the build's own version. It must work for a stable tag as well as for an rc tag: the
first stable release (v1.0.0) failed because the block accepted only ``X.Y.Z-rc.N``.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "packaging" / "linux-image" / "install-proof.sh"


def update_versions(version: str) -> tuple[int, str]:
    text = SCRIPT.read_text(encoding="utf-8")
    block = re.search(r"# update-versions:start\n(.*?)# update-versions:end\n", text, re.S)
    assert block is not None, "install-proof.sh has no update-versions block"
    program = (
        'fail() { echo "FAILED: $*"; exit 1; }\n'
        f"version={version}\n{block.group(1)}"
        'echo "$bad $good"\n'
    )
    result = subprocess.run(["bash", "-c", program], capture_output=True, text=True, check=False)
    return result.returncode, result.stdout.strip()


class UpdateProofVersionTests(unittest.TestCase):
    def test_an_rc_build_proves_the_update_with_the_next_two_rc_numbers(self):
        self.assertEqual(update_versions("0.1.0-rc.42"), (0, "0.1.0-rc.43 0.1.0-rc.44"))

    def test_a_stable_build_proves_the_update_with_rc_versions_of_the_next_patch(self):
        self.assertEqual(update_versions("1.0.0"), (0, "1.0.1-rc.1 1.0.1-rc.2"))
        self.assertEqual(update_versions("2.3.9"), (0, "2.3.10-rc.1 2.3.10-rc.2"))


if __name__ == "__main__":
    unittest.main()
