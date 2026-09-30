"""Run one shard of the Python suite; Windows CI splits it across jobs.

    python -m tests.ci_shard INDEX TOTAL

Every test module runs in exactly one shard. Slowest modules go first, each to
the lightest shard. Each module is discovered as `unittest discover -s tests`
would, and its time is printed so SECONDS can be updated when shards drift.
"""
import sys
import time
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
# ponytail: measured seconds (local run, 2026-09-30) for modules at 20s or more;
# any other module counts as DEFAULT. Refresh from a CI shard printout.
SECONDS = {
    "test_dispatch_driver.py": 356, "test_trust_evidence.py": 300, "test_archive_milestone.py": 171,
    "test_git_guard.py": 120, "test_isolation.py": 79, "test_member_undo.py": 45,
    "test_member_round.py": 43, "test_member_landing.py": 34, "test_install.py": 34,
    "test_model_policy.py": 30, "test_rebase_recovery.py": 27, "test_runtime_lifecycle.py": 25,
    "test_pipeline_undo.py": 25, "test_member_landing_proof.py": 25, "test_pipeline_state.py": 23,
    "test_members.py": 23, "test_member_activation.py": 22, "test_build_reentry.py": 21,
    "test_workflow_run.py": 20,
}
DEFAULT = 5


def modules(index=0, total=1):
    if not 0 <= index < total:
        raise SystemExit("usage: python -m tests.ci_shard INDEX TOTAL (0 <= INDEX < TOTAL)")
    names = sorted(path.name for path in TESTS.glob("test*.py"))
    shards, loads = [[] for _ in range(total)], [0] * total
    for name in sorted(names, key=lambda item: (-SECONDS.get(item, DEFAULT), item)):
        lightest = loads.index(min(loads))
        shards[lightest].append(name)
        loads[lightest] += SECONDS.get(name, DEFAULT)
    return sorted(shards[index])


def run(names, directory=TESTS):
    failed, timings = False, []
    for name in names:
        start = time.monotonic()
        # A fresh loader per module: a reused one keeps the first top-level dir.
        suite = unittest.TestLoader().discover(str(directory), pattern=name)
        failed = not unittest.TextTestRunner().run(suite).wasSuccessful() or failed
        timings.append((time.monotonic() - start, name))
    for seconds, name in sorted(timings, reverse=True):
        print(f"{seconds:8.1f}s  {name}")
    return 1 if failed else 0


def main(argv=None):
    index, total = (int(value) for value in (sys.argv[1:] if argv is None else argv))
    return run(modules(index, total))


if __name__ == "__main__":
    raise SystemExit(main())
