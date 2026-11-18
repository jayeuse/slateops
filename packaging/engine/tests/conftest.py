"""Engine tests import the W5a modules from backend/ only to compare rules (AC-L8)."""

import sys
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[3] / "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)
