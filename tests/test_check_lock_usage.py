import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CheckLockUsageTests(unittest.TestCase):
    def test_no_blocking_lk_lock_outside_common(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_lock_usage.py")],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
