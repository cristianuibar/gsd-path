"""Project setup actions for the app: hooks, health check, and member repair.

The daemon only chooses the helper command; the helper owns every rule.
"""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "daemon"))

from gsd_daemon import project_ops
from gsd_daemon.plugin import PluginManager


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = str(self.base / "coordinator")
        self.member = str(self.base / "member-api")
        self.calls = []
        self.answers = {}  # first helper argument after the script -> (rc, stdout, stderr)

        def runner(argv, cwd=None):
            argv = [str(part) for part in argv]
            self.calls.append(argv)
            script = Path(argv[1]).name
            key = (script, argv[2])
            return self.answers.get(key, (0, "done\n", ""))

        self.plugin = PluginManager(home=self.base / "home", user_home=self.base / "user", runner=runner,
                                    git_runner=lambda argv, cwd=None: (0, "", ""), environ={},
                                    repo="https://example.invalid/gsd-path.git")
        (self.plugin.src_dir / ".git").mkdir(parents=True)
        self.handler = SimpleNamespace(plugin=self.plugin, watcher=SimpleNamespace(projects={self.root: object()}))
        self.members = {"members": [{"name": "api", "checkout": self.member, "remote": "git@x:api.git",
                                     "integration": "default"}]}

    def run_op(self, **body):
        return project_ops.run(self.handler, {"root": self.root, **body})

    def helper_args(self):
        return [call[2:] for call in self.calls]


class InstallerOpTests(Case):
    def test_each_op_runs_its_installer_flag_on_the_project(self):
        for op, flag in (("hooks-init", "--hooks-init"), ("hooks-refresh", "--hooks-refresh"),
                         ("hooks-refresh-full", "--hooks-refresh-full"), ("runtime-restore", "--runtime-restore")):
            with self.subTest(op=op):
                self.calls.clear()
                result = self.run_op(op=op)
                self.assertTrue(result["ok"], result)
                self.assertEqual(self.calls, [[sys.executable, str(self.plugin.install_py), flag, "--project", self.root]])

    def test_dry_run_adds_the_installer_preview_flag(self):
        self.run_op(op="hooks-refresh", dry_run=True)
        self.assertEqual(self.helper_args(), [["--hooks-refresh", "--project", self.root, "--dry-run"]])

    def test_health_check_returns_findings_even_when_the_installer_reports_problems(self):
        self.answers[("install.py", "--doctor")] = (1, "note: codex: not installed\n1 problem found.\n",
                                                    "error: claude: incomplete install\n")
        result = self.run_op(op="doctor")
        self.assertEqual(self.helper_args(), [["--doctor", "--project", self.root]])
        self.assertFalse(result["ok"])
        self.assertIn("1 problem found.", result["stdout_tail"])
        self.assertIn("incomplete install", result["error"])

    def test_an_unwatched_project_or_unknown_op_runs_nothing(self):
        for body in ({"root": "/etc", "op": "doctor"}, {"op": "rm -rf"}, {"op": None}, {"root": 5, "op": "doctor"}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                project_ops.run(self.handler, {"root": self.root, **body})
        self.assertEqual(self.calls, [])

    def test_a_second_operation_is_refused_while_one_runs(self):
        release = threading.Event()
        started = threading.Event()
        inner = self.plugin.runner

        def slow(argv, cwd=None):
            started.set()
            release.wait(5)
            return inner(argv, cwd)
        self.plugin.runner = slow
        first = threading.Thread(target=lambda: self.run_op(op="doctor"))
        first.start()
        self.assertTrue(started.wait(5))
        try:
            with self.assertRaises(project_ops.Busy) as raised:
                self.run_op(op="hooks-refresh")
            self.assertEqual(raised.exception.status, 409)
        finally:
            release.set()
            first.join(5)
        self.assertEqual(len(self.calls), 1)


class MemberTests(Case):
    def test_members_lists_each_member_with_marker_and_hook_state(self):
        self.answers[("members.py", "validate")] = (0, json.dumps(self.members), "")
        self.answers[("members.py", "detect")] = (0, json.dumps(
            {"member": True, "current": True, "checkout": self.member, "coordinator": self.root,
             "project": "demo", "name": "api"}), "")
        result = self.run_op(op="members")
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.helper_args(), [["validate", "--repo", self.root], ["detect", "--checkout", self.member]])
        row = result["members"][0]
        self.assertEqual((row["name"], row["checkout"], row["integration"]), ("api", self.member, "default"))
        self.assertEqual(row["marker"], {"current": True, "reason": None})
        self.assertIn("hooks", row)

    def test_a_failed_validation_returns_the_helper_text_with_its_fix(self):
        text = f"error: member marker for api is missing or stale; run members.py repair --repo {self.root}\n"
        self.answers[("members.py", "validate")] = (1, "", text)
        result = self.run_op(op="members")
        self.assertEqual((result["ok"], result["members"]), (False, []))
        self.assertIn("run members.py repair", result["error"])

    def test_repair_runs_the_helper_and_has_no_preview(self):
        self.answers[("members.py", "repair")] = (0, json.dumps(self.members), "")
        result = self.run_op(op="member-repair")
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.helper_args(), [["repair", "--repo", self.root]])
        self.calls.clear()
        with self.assertRaises(ValueError):
            self.run_op(op="member-repair", dry_run=True)
        self.assertEqual(self.calls, [])

    def test_member_hooks_install_only_into_a_recorded_member(self):
        self.answers[("members.py", "validate")] = (0, json.dumps(self.members), "")
        result = self.run_op(op="member-hooks", member=self.member, dry_run=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.helper_args()[-1], ["--member-of", self.root, "--project", self.member, "--dry-run"])
        self.calls.clear()
        with self.assertRaises(ValueError):
            self.run_op(op="member-hooks", member=str(self.base / "elsewhere"))
        self.assertNotIn("--member-of", [arg for call in self.calls for arg in call])


if __name__ == "__main__":
    unittest.main()
