#!/usr/bin/env python3
# gsd-path project runtime
"""Refuse blocking Windows msvcrt LK_LOCK outside the shared lock helper."""

from __future__ import annotations

import re
import sys

sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP = {"_common.py", "check_lock_usage.py"}


def main() -> int:
    problems: list[str] = []
    for path in sorted(ROOT.glob("*.py")):
        if path.name in SKIP:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\bLK_LOCK\b", text):
            problems.append(str(path.relative_to(ROOT.parent)))
    if problems:
        print("LK_LOCK must not appear outside scripts/_common.py:", file=sys.stderr)
        print("Use _common.exclusive_lock or msvcrt.LK_NBLCK with polling instead.", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
