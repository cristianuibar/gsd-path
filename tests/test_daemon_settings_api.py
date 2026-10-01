"""The app's Settings pages read and change daemon.json through the daemon."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "daemon"))

from gsd_daemon.config import Config
from gsd_daemon.plugin import PluginManager
from gsd_daemon.serve import serve
from gsd_daemon.watcher import Watcher


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.config_path = self.root / "daemon.json"
        env = mock.patch.dict(os.environ, {"GSD_DAEMON_CONFIG": str(self.config_path)})
        env.start()
        self.addCleanup(env.stop)
        self.sessions = self.root / "sessions"
        self.sessions.mkdir()
        self.watcher = Watcher(Config(parents=[], history=False, session_dirs=[]))
        self.plugin = PluginManager(home=self.root / "home", user_home=self.root / "user", environ={},
                                    runner=lambda argv, cwd=None: (0, "", ""))
        self.scans = []
        with mock.patch("threading.Thread.start"):  # no background poll
            self.server = serve(self.watcher, port=0, plugin=self.plugin)
        self.server.RequestHandlerClass.scan = staticmethod(lambda scan_sessions=True: self.scans.append(scan_sessions))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def request(self, method, path, body=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        send = {"Content-Type": "application/json"} if body is not None or raw is not None else {}
        connection.request(method, path, body=raw if raw is not None else None if body is None else json.dumps(body),
                           headers={**send, **(headers or {})})
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def saved(self):
        return json.loads(self.config_path.read_text(encoding="utf-8"))


class ConfigRouteTests(Case):
    def test_get_returns_every_setting(self):
        status, payload = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(payload, self.watcher.config.to_dict())
        self.assertEqual(sorted(payload), ["excludes", "history", "max_depth", "notify", "parents",
                                           "poll_seconds", "prices", "session_dirs"])

    def test_changes_are_saved_applied_and_scanned(self):
        skip = self.root / "skip"
        changes = {"excludes": [str(skip)], "max_depth": 3, "poll_seconds": 30, "notify": False,
                   "history": True, "session_dirs": [str(self.sessions)],
                   "prices": {"gpt-x": {"input": 1.25, "cached": 0.125, "output": 10}}}
        status, payload = self.request("POST", "/api/config", changes)
        self.assertEqual(status, 200, payload)
        for key, value in changes.items():
            self.assertEqual(payload[key], value, key)
            self.assertEqual(self.saved()[key], value, key)
            self.assertEqual(getattr(self.watcher.config, key), value, key)
        # The running session index uses the new folders and prices on the next scan.
        self.assertEqual(self.watcher.sessions.dirs, [str(self.sessions)])
        self.assertEqual(self.watcher.sessions.prices, changes["prices"])
        # The request scans projects only; the next background poll reads the session logs.
        self.assertEqual(self.scans, [False])

    def test_change_waits_for_a_scan_in_progress(self):
        done = threading.Event()
        answer = []

        def post():
            answer.append(self.request("POST", "/api/config", {"session_dirs": [str(self.sessions)]}))
            done.set()

        with self.server.RequestHandlerClass.scan_lock:  # a background poll holds this lock while it scans
            threading.Thread(target=post, daemon=True).start()
            self.assertFalse(done.wait(0.5))
            self.assertEqual(self.watcher.sessions.dirs, [])
            self.assertEqual(self.watcher.config.session_dirs, [])
        self.assertTrue(done.wait(5))
        self.assertEqual(answer[0][0], 200, answer)
        self.assertEqual(self.watcher.sessions.dirs, [str(self.sessions)])

    def test_one_key_changes_only_that_key(self):
        before = self.watcher.config.to_dict()
        status, payload = self.request("POST", "/api/config", {"poll_seconds": 9})
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload, {**before, "poll_seconds": 9})

    def test_bad_values_are_refused_and_nothing_changes(self):
        before = self.watcher.config.to_dict()
        bad = [{"max_depth": 0}, {"max_depth": True}, {"poll_seconds": -1}, {"poll_seconds": "5"},
               {"notify": "yes"}, {"excludes": "/tmp"}, {"excludes": [""]}, {"session_dirs": [3]},
               {"prices": {"m": {"input": -1}}}, {"prices": {"m": {"input": "1"}}},
               {"prices": {"m": {"speed": 1}}}, {"prices": []}, {"theme": "dark"},
               {"prices": {"m": {"input": float("nan")}}}, {"prices": {"m": {"output": float("inf")}}},
               {"prices": {"m": {"cached": 10 ** 400}}},
               {"poll_seconds": 9, "max_depth": 0}]
        for body in bad:
            with self.subTest(body=body):
                status, payload = self.request("POST", "/api/config", body)
                self.assertEqual(status, 400, payload)
                self.assertIn("error", payload)
        self.assertEqual(self.watcher.config.to_dict(), before)
        self.assertFalse(self.config_path.exists())
        self.assertEqual(self.scans, [])

    def test_body_that_is_not_a_json_object_is_refused(self):
        for raw in ("[1]", "{not json"):
            with self.subTest(raw=raw):
                status, payload = self.request("POST", "/api/config", raw=raw)
                self.assertEqual((status, payload), (400, {"error": "invalid JSON body"}))
        self.assertEqual(self.scans, [])

    def test_failed_save_changes_nothing_in_the_running_daemon(self):
        before = self.watcher.config.to_dict()
        with mock.patch.object(Config, "save", side_effect=OSError("disk full")):
            status, payload = self.request("POST", "/api/config", {
                "poll_seconds": 9, "session_dirs": [str(self.sessions)], "prices": {"m": {"input": 1}}})
        self.assertEqual((status, payload), (500, {"error": "disk full"}))
        self.assertEqual(self.watcher.config.to_dict(), before)
        self.assertEqual(self.watcher.sessions.dirs, [])
        self.assertEqual(self.watcher.sessions.prices, {})
        self.assertEqual(self.scans, [])

    def test_removed_session_folder_no_longer_counts_in_project_usage(self):
        project = self.root / "proj"
        project.mkdir()
        line = {"type": "assistant", "cwd": str(project), "timestamp": "2026-09-01T09:00:05.000Z", "uuid": "a1",
                "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 10, "output_tokens": 20}}}
        folders = [self.root / "kept", self.root / "removed"]
        for folder in folders:
            folder.mkdir()
            (folder / "session.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
        status, payload = self.request("POST", "/api/config", {"session_dirs": [str(f) for f in folders]})
        self.assertEqual(status, 200, payload)
        self.watcher.sessions.scan([str(project)])
        self.assertEqual(len(self.watcher.sessions.records_for(str(project))), 2)
        status, payload = self.request("POST", "/api/config", {"session_dirs": [str(folders[0])]})
        self.assertEqual(status, 200, payload)
        self.assertEqual(len(self.watcher.sessions.records_for(str(project))), 1)

    def test_get_routes_refuse_a_foreign_host_or_origin(self):
        for path in ("/api/config", "/api/diagnostics"):
            for headers in ({"Host": f"evil.example:{self.port}"}, {"Origin": "https://evil.example"},
                            {"Sec-Fetch-Site": "cross-site"}):
                with self.subTest(path=path, headers=headers):
                    status, payload = self.request("GET", path, headers=headers)
                    self.assertEqual(status, 403, payload)
                    self.assertEqual(list(payload), ["error"])
            status, _payload = self.request("GET", path, headers={
                "Host": f"localhost:{self.port}", "Origin": f"http://localhost:{self.port}"})
            self.assertEqual(status, 200)

    def test_cross_site_write_is_refused(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("POST", "/api/config", body=json.dumps({"poll_seconds": 9}),
                           headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
        self.assertEqual(connection.getresponse().status, 403)
        connection.close()
        self.assertEqual(self.watcher.config.poll_seconds, 5)


class DiagnosticsTests(Case):
    def test_report_has_versions_config_and_log_tail(self):
        logs = self.root / "home" / "logs"
        logs.mkdir(parents=True)
        (logs / "plugin.log").write_text("".join(f"line {n}\n" for n in range(100)), encoding="utf-8")
        status, payload = self.request("GET", "/api/diagnostics")
        self.assertEqual(status, 200)
        from gsd_daemon import __version__
        self.assertEqual(payload["daemon_version"], __version__)
        self.assertEqual(payload["python_version"], ".".join(str(part) for part in sys.version_info[:3]))
        self.assertEqual(payload["config"], self.watcher.config.to_dict())
        self.assertEqual(payload["projects"], 0)
        tail = payload["logs"]["plugin.log"]
        self.assertTrue(tail.endswith("line 99"))
        self.assertNotIn("line 0\n", tail)

    def test_report_never_holds_the_write_token(self):
        app = self.root / "home" / "app"
        app.mkdir(parents=True)
        (app / "api-token").write_text("s3cret-token-value", encoding="utf-8")
        status, payload = self.request("GET", "/api/diagnostics")
        self.assertEqual(status, 200)
        self.assertNotIn("s3cret-token-value", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
