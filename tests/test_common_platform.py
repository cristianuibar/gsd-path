import multiprocessing
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import _common
from _platform import WINDOWS, fake_cli, posix_only, requires_bash, windows_only


def _hold_lock(path: str, ready, release) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import _common as common

    with common.exclusive_lock(Path(path)):
        ready.set()
        release.wait(30)


class AtomicWriteTests(unittest.TestCase):
    def test_writes_lf_bytes_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "STATE.md"
            _common.atomic_write(path, "one\ntwo\n")
            self.assertEqual(path.read_bytes(), b"one\ntwo\n")
            self.assertFalse((Path(directory) / ".STATE.md.gsd-path-tmp").exists())

    def test_writes_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.md"
            _common.atomic_write(path, "café ✓\n")
            self.assertEqual(path.read_bytes(), "café ✓\n".encode("utf-8"))

    @windows_only
    def test_replaces_while_a_reader_holds_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "STATE.md"
            path.write_bytes(b"old\n")
            reader = open(path, "rb")
            threading_release = threading.Timer(0.2, reader.close)
            threading_release.start()
            try:
                _common.atomic_write(path, "new\n")
            finally:
                threading_release.join()
                reader.close()
            self.assertEqual(path.read_bytes(), b"new\n")


class ReplaceTests(unittest.TestCase):
    def test_non_busy_error_is_not_retried(self) -> None:
        error = PermissionError(13, "denied")
        error.winerror = 1920
        with mock.patch.object(_common.os, "name", "nt"), \
                mock.patch.object(_common.os, "replace", side_effect=error) as replace:
            with self.assertRaises(PermissionError):
                _common.replace(Path("a"), Path("b"))
        self.assertEqual(replace.call_count, 1)

    def test_busy_error_is_retried(self) -> None:
        error = PermissionError(13, "busy")
        error.winerror = 32
        with mock.patch.object(_common.os, "name", "nt"), \
                mock.patch.object(_common.time, "sleep"), \
                mock.patch.object(_common.os, "replace", side_effect=[error, error, None]) as replace:
            _common.replace(Path("a"), Path("b"))
        self.assertEqual(replace.call_count, 3)


class FsyncDirectoryTests(unittest.TestCase):
    def test_accepts_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _common.fsync_directory(Path(directory))


class ExclusiveLockTests(unittest.TestCase):
    def test_second_process_is_refused_while_held(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.lock"
            context = multiprocessing.get_context("spawn")
            ready, release = context.Event(), context.Event()
            holder = context.Process(target=_hold_lock, args=(str(path), ready, release))
            holder.start()
            try:
                self.assertTrue(ready.wait(30))
                with self.assertRaises(BlockingIOError):
                    with _common.exclusive_lock(path, blocking=False):
                        pass
                with self.assertRaises(TimeoutError):
                    with _common.exclusive_lock(path, timeout=0.2):
                        pass
            finally:
                release.set()
                holder.join(30)
            with _common.exclusive_lock(path, blocking=False):
                pass

    def test_creates_parent_and_can_be_reacquired(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "state.lock"
            with _common.exclusive_lock(path):
                self.assertTrue(path.exists())
            with _common.exclusive_lock(path):
                pass


class ProcessAliveTests(unittest.TestCase):
    def test_current_process_is_alive(self) -> None:
        self.assertTrue(_common.process_alive(os.getpid()))

    def test_exited_process_is_not_alive(self) -> None:
        exited = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                                capture_output=True, text=True, check=True)
        self.assertFalse(_common.process_alive(int(exited.stdout)))

    def test_invalid_pids_are_not_alive(self) -> None:
        self.assertFalse(_common.process_alive(0))
        self.assertFalse(_common.process_alive(-1))

    @windows_only
    def test_never_signals_on_windows(self) -> None:
        with mock.patch.object(_common.os, "kill") as kill:
            _common.process_alive(os.getpid())
        kill.assert_not_called()


class KillTreeTests(unittest.TestCase):
    def test_kills_child_and_grandchild(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "grandchild.pid"
            script = textwrap.dedent(f"""
                import subprocess, sys, time
                grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
                open({str(pid_file)!r}, "w").write(str(grandchild.pid))
                time.sleep(60)
            """)
            process = _common.popen_group([sys.executable, "-c", script])
            try:
                deadline = time.monotonic() + 30
                while not pid_file.exists() or not pid_file.read_text():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
                grandchild = int(pid_file.read_text())
                self.assertTrue(_common.process_alive(grandchild))
                _common.kill_tree(process)
                process.wait(30)
                deadline = time.monotonic() + 10
                while _common.process_alive(grandchild) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(_common.process_alive(grandchild))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


class BashTests(unittest.TestCase):
    @posix_only
    def test_posix_uses_bash_from_path(self) -> None:
        self.assertEqual(_common.bash_argv("true"), ["bash", "-c", "true"])

    @windows_only
    def test_windows_never_picks_the_wsl_launcher(self) -> None:
        system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "bash.exe")
        with mock.patch.dict(os.environ, {}, clear=False) as environment, \
                mock.patch.object(_common.shutil, "which",
                                  side_effect=lambda name: system32 if name == "bash" else None), \
                mock.patch.object(_common.os.path, "isfile", side_effect=lambda path: path == system32):
            environment.pop("GSD_PATH_BASH", None)
            with self.assertRaises(_common.ShellNotFound):
                _common.find_bash()

    @windows_only
    def test_windows_override_must_exist(self) -> None:
        with mock.patch.dict(os.environ, {"GSD_PATH_BASH": r"C:\missing\bash.exe"}):
            with self.assertRaises(_common.ShellNotFound):
                _common.find_bash()

    @requires_bash
    def test_runs_a_bash_command(self) -> None:
        result = subprocess.run(_common.bash_argv('printf "%s" "$((1 + 2))"'),
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "3")


class ResolveArgvTests(unittest.TestCase):
    @posix_only
    def test_posix_is_unchanged(self) -> None:
        self.assertEqual(_common.resolve_argv(["codex", "exec"]), ["codex", "exec"])

    @windows_only
    def test_windows_finds_cmd_shims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shim = fake_cli(Path(directory), "fakecli", "import sys; print('ok', *sys.argv[1:])")
            with mock.patch.dict(os.environ, {"PATH": directory + os.pathsep + os.environ["PATH"]}):
                argv = _common.resolve_argv(["fakecli", "one"])
                self.assertEqual(Path(argv[0]).resolve(), shim.resolve())
                result = subprocess.run(argv, capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.strip(), "ok one")
                with self.assertRaises(ValueError):
                    _common.resolve_argv(["fakecli", "a & calc"])

    @windows_only
    def test_windows_missing_command(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _common.resolve_argv(["gsd-path-no-such-command"])


class SplitCommandTests(unittest.TestCase):
    def test_splits_quoted_arguments(self) -> None:
        self.assertEqual(_common.split_command('coder --flag "two words"'),
                         ["coder", "--flag", "two words"])

    def test_empty(self) -> None:
        self.assertEqual(_common.split_command("   "), [])

    @windows_only
    def test_keeps_windows_backslashes(self) -> None:
        self.assertEqual(
            _common.split_command(r'C:\Python312\python.exe "C:\Program Files\x\coder.py" -v'),
            [r"C:\Python312\python.exe", r"C:\Program Files\x\coder.py", "-v"],
        )


class RmtreeForceTests(unittest.TestCase):
    def test_removes_read_only_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory) / "tree"
            (tree / "objects").mkdir(parents=True)
            target = tree / "objects" / "pack"
            target.write_bytes(b"x")
            target.chmod(0o444)
            _common.rmtree_force(tree)
            self.assertFalse(tree.exists())


class GitOutputEncodingTests(unittest.TestCase):
    def test_non_ascii_paths_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "café.md").write_text("x", encoding="utf-8")
            result = _common.run_git(repo, "-c", "core.quotepath=false", "ls-files", "--others", "-z")
            self.assertEqual(result.stdout.split("\0")[0], "café.md")


if __name__ == "__main__":
    unittest.main()
