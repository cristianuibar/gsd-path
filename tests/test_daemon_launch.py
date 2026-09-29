import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

DAEMON = Path(__file__).resolve().parents[1] / "daemon"
sys.path.insert(0, str(DAEMON))

from gsd_daemon import __version__
from gsd_daemon import launch as launch_module
from gsd_daemon.config import Config
from gsd_daemon.installer import Installer
from gsd_daemon.launch import RETIRED_MARKER, ensure_venv, launch, probe_port
from gsd_daemon.serve import serve
from gsd_daemon.watcher import Watcher

UNIX_ONLY = unittest.skipIf(sys.platform == "win32", "uses ps, lsof, and POSIX signals")

# A process that answers /status like a GSD Path daemon but is not one.
IMPOSTOR = r"""
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"schema": "gsd-path-daemon/status/v1",
                           "daemon": {"version": "0.0.1", "pid": os.getpid()}}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ScriptRunner:
    """Answers commands from a script; runs `real` commands for real."""

    def __init__(self, respond=None, which=None, real=()):
        self.calls = []
        self.respond = respond or (lambda cmd: (0, ""))
        self.which_map = which if which is not None else {"git": "/usr/bin/git"}
        self.real = set(real)

    def run(self, cmd, check=True):
        cmd = [str(part) for part in cmd]
        self.calls.append(cmd)
        if Path(cmd[0]).name in self.real:
            return subprocess.run(cmd, check=check, capture_output=True, text=True)
        returncode, stdout = self.respond(cmd)
        if check and returncode:
            raise subprocess.CalledProcessError(returncode, cmd, stdout, "pip: network is down")
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")

    def which(self, name):
        if name in self.real:
            return name
        return self.which_map.get(name)

    def ran(self, word):
        return [cmd for cmd in self.calls if any(word in part for part in cmd)]


def installed(version):
    """Respond as a venv whose installed daemon is `version`."""
    def respond(cmd):
        if "importlib.metadata" in " ".join(cmd):
            return (0, version + "\n") if version else (1, "")
        return 0, ""
    return respond


class LaunchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def installer(self, runner, platform=None, retired=True, fake_venv=True):
        installer = Installer(
            home=self.home,
            launch_agents_dir=self.home / "LaunchAgents",
            startup_dir=self.home / "startup",
            systemd_user_dir=self.home / "systemd",
            runner=runner,
            platform=platform or sys.platform,
            repo_root=DAEMON.parent,
            out=lambda _line: None,
        )
        if retired:
            marker = installer.gsd_home / RETIRED_MARKER
            marker.parent.mkdir(parents=True)
            marker.write_text("done\n")
        if fake_venv:
            installer.venv_python.parent.mkdir(parents=True)
            installer.venv_python.write_text("")
        return installer

    def spawn(self, argv, port):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                   PYTHONPATH=str(DAEMON))
        process = subprocess.Popen(argv + [str(port)], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (process.poll() is None and process.kill(), process.wait()))
        deadline = time.monotonic() + 30
        while probe_port(port)["state"] == "free":
            self.assertLess(time.monotonic(), deadline, "server did not start")
            self.assertIsNone(process.poll(), "server exited early")
            time.sleep(0.1)
        return process

    def serve_in_thread(self, handler=None):
        if handler is None:
            server = serve(Watcher(Config(parents=[self.tmp.name], history=False)), port=0)
            self.addCleanup(server.watcher_stop.set)
        else:
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]


class ProbeTests(LaunchCase):
    def test_free_port(self):
        self.assertEqual(probe_port(free_port()), {"state": "free"})

    def test_gsd_daemon_reports_version_and_pid(self):
        port = self.serve_in_thread()
        self.assertEqual(probe_port(port),
                         {"state": "daemon", "version": __version__, "pid": os.getpid()})

    def test_other_http_service(self):
        port = self.serve_in_thread(SimpleHTTPRequestHandler)
        self.assertEqual(probe_port(port), {"state": "other"})


class RunningDaemonTests(LaunchCase):
    def test_same_version_daemon_is_reused(self):
        runner = ScriptRunner(installed(__version__))
        port = self.serve_in_thread()
        result = launch(port, self.installer(runner))
        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["problems"], [])
        self.assertEqual(runner.ran("pip"), [])

    def test_newer_running_daemon_is_reused_over_older_bundle(self):
        runner = ScriptRunner(installed("0.0.9"))
        port = self.serve_in_thread()
        with mock.patch.object(launch_module, "__version__", "0.0.9"):
            result = launch(port, self.installer(runner))
        self.assertEqual((result["action"], result["version"]), ("reuse", __version__))

    @UNIX_ONLY
    def test_older_daemon_process_is_stopped_then_started(self):
        port = free_port()
        old = self.spawn([sys.executable, "-m", "gsd_daemon", "serve", "--port"], port)
        runner = ScriptRunner(installed("9.0.0"), real=("ps", "lsof", "ss"))
        with mock.patch.object(launch_module, "__version__", "9.0.0"):
            result = launch(port, self.installer(runner))
        self.assertEqual(result["action"], "start", result["problems"])
        self.assertEqual(result["serve_argv"][-2:], ["--port", str(port)])
        self.assertIsNotNone(old.wait(timeout=5))
        self.assertEqual(probe_port(port), {"state": "free"})

    @UNIX_ONLY
    def test_impostor_with_daemon_schema_is_never_stopped(self):
        port = free_port()
        impostor = self.spawn([sys.executable, "-c", IMPOSTOR], port)
        runner = ScriptRunner(installed(__version__), real=("ps", "lsof", "ss"))
        result = launch(port, self.installer(runner))
        self.assertEqual(result["action"], "setup")
        self.assertEqual([(p["kind"], p["blocking"]) for p in result["problems"]], [("port", True)])
        self.assertIsNone(impostor.poll())

    def test_other_service_on_port_blocks_without_install(self):
        runner = ScriptRunner(installed(None))
        port = self.serve_in_thread(SimpleHTTPRequestHandler)
        result = launch(port, self.installer(runner, fake_venv=False))
        self.assertEqual(result["action"], "setup")
        self.assertEqual([p["kind"] for p in result["problems"]], ["port"])
        self.assertEqual(runner.ran("pip"), [])

    def test_free_port_starts_daemon(self):
        runner = ScriptRunner(installed(__version__))
        installer = self.installer(runner)
        port = free_port()
        result = launch(port, installer)
        self.assertEqual(result["action"], "start")
        self.assertEqual(result["serve_argv"],
                         [str(installer.venv_python), "-m", "gsd_daemon", "serve", "--port", str(port)])


class VenvTests(LaunchCase):
    def test_newer_installed_daemon_is_never_downgraded(self):
        runner = ScriptRunner(installed("99.0.0"))
        self.assertEqual(ensure_venv(self.installer(runner)), "99.0.0")
        self.assertEqual(runner.ran("pip"), [])
        self.assertEqual([cmd for cmd in runner.calls if cmd[1:3] == ["-m", "venv"]], [])

    def test_older_installed_daemon_is_upgraded_from_bundle(self):
        runner = ScriptRunner(installed("0.0.1"))
        installer = self.installer(runner)
        self.assertEqual(ensure_venv(installer), __version__)
        self.assertEqual(runner.ran("pip")[0][-1], str(DAEMON))

    def test_install_failure_is_a_blocking_problem(self):
        def respond(cmd):
            return (1, "") if cmd[1:3] == ["install", "--upgrade"] else installed(None)(cmd)
        result = launch(free_port(), self.installer(ScriptRunner(respond)))
        self.assertEqual(result["action"], "setup")
        self.assertEqual([p["kind"] for p in result["problems"]], ["install"])
        self.assertIn("network is down", result["problems"][0]["fix"])


class PrerequisiteTests(LaunchCase):
    def test_missing_git_blocks(self):
        runner = ScriptRunner(installed(__version__), which={})
        result = launch(free_port(), self.installer(runner))
        self.assertEqual(result["action"], "setup")
        self.assertEqual([(p["kind"], p["blocking"]) for p in result["problems"]], [("git", True)])
        self.assertEqual(runner.ran("pip"), [])


class LegacyAutostartTests(LaunchCase):
    def darwin(self, still_loaded, login_items="Finder"):
        state = {"uninstalled": False}

        def respond(cmd):
            if cmd[:2] == ["launchctl", "bootout"]:
                state["uninstalled"] = True
            if cmd[:2] == ["launchctl", "print"]:
                return (0, "") if (still_loaded or not state["uninstalled"]) else (113, "")
            if cmd[0] == "osascript" and "get the name" in cmd[-1]:
                return 0, login_items
            return installed(__version__)(cmd)
        return ScriptRunner(respond)

    def test_uninstall_is_rechecked_and_remaining_entry_is_reported(self):
        runner = self.darwin(still_loaded=True)
        installer = self.installer(runner, platform="darwin", retired=False)
        installer.plist_path.parent.mkdir(parents=True)
        installer.plist_path.write_text("<plist/>")
        result = launch(free_port(), installer)
        self.assertTrue(runner.ran("bootout"), "uninstall did not run")
        self.assertFalse(installer.plist_path.exists())
        self.assertEqual(result["action"], "start")
        self.assertFalse(result["autostart_ok"])
        self.assertEqual([(p["kind"], p["blocking"]) for p in result["problems"]],
                         [("autostart", False)])
        self.assertFalse((installer.gsd_home / RETIRED_MARKER).exists())

    def test_verified_cleanup_writes_marker_and_later_launch_skips_checks(self):
        runner = self.darwin(still_loaded=False, login_items="Finder, GSDPathTray")
        installer = self.installer(runner, platform="darwin", retired=False)
        first = launch(free_port(), installer)
        self.assertTrue(runner.ran("delete login item"), "login item was not removed")
        # The fake still lists the login item after removal, so it remains.
        self.assertEqual([p["kind"] for p in first["problems"]], ["autostart"])

        clean = self.darwin(still_loaded=False)
        installer.runner = clean
        second = launch(free_port(), installer)
        self.assertTrue(second["autostart_ok"])
        self.assertTrue((installer.gsd_home / RETIRED_MARKER).exists())

        skipped = self.darwin(still_loaded=True)
        installer.runner = skipped
        third = launch(free_port(), installer)
        self.assertTrue(third["autostart_ok"])
        self.assertEqual(skipped.ran("launchctl"), [])

    def test_login_item_is_not_checked_without_a_previous_install(self):
        runner = self.darwin(still_loaded=False)
        installer = self.installer(runner, platform="darwin", retired=False, fake_venv=False)
        launch_module.retire_legacy(installer)
        self.assertTrue(runner.ran("bootout"), "uninstall did not run")
        self.assertEqual(runner.ran("get the name"), [])

    def test_windows_startup_shortcut_is_removed(self):
        runner = ScriptRunner(installed(__version__))
        installer = self.installer(runner, platform="win32", retired=False)
        installer.shortcut_path.parent.mkdir(parents=True)
        installer.shortcut_path.write_text("lnk")
        self.assertEqual(launch_module.retire_legacy(installer), [])
        self.assertFalse(installer.shortcut_path.exists())


class CliTests(LaunchCase):
    def test_launch_command_prints_json(self):
        marker = self.home / ".gsd-path" / RETIRED_MARKER
        marker.parent.mkdir(parents=True)
        marker.write_text("done\n")
        port = self.serve_in_thread(SimpleHTTPRequestHandler)
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                   PYTHONPATH=str(DAEMON))
        output = subprocess.run([sys.executable, "-m", "gsd_daemon", "launch", "--port", str(port)],
                                env=env, capture_output=True, text=True, check=True).stdout
        result = json.loads(output)
        self.assertEqual((result["action"], result["port"]), ("setup", port))
        self.assertEqual([p["kind"] for p in result["problems"]], ["port"])


if __name__ == "__main__":
    unittest.main()
