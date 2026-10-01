"""Routes the native app's Skills, Project, and Environment pages call."""
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
from gsd_daemon.model import ProjectStatus
from gsd_daemon.plugin import HOSTS, OP_LOCK, PluginManager
from gsd_daemon.serve import TOKEN_HEADER, serve
from gsd_daemon.watcher import Watcher

TOKEN = "s3cret"


class Case(unittest.TestCase):
    token = TOKEN

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GSD_DAEMON_CONFIG": str(self.base / "daemon.json")})
        env.start()
        self.addCleanup(env.stop)
        self.project = self.base / "project"
        self.project.mkdir()
        self.calls = []

        def runner(argv, cwd=None):
            self.calls.append([str(part) for part in argv])
            return 0, "done\n", ""
        self.plugin = PluginManager(home=self.base / "home", user_home=self.base / "user", runner=runner,
                                    git_runner=lambda argv, cwd=None: (0, "", ""), environ={},
                                    repo="https://example.invalid/gsd-path.git")
        (self.plugin.src_dir / ".git").mkdir(parents=True)
        watcher = Watcher(Config(parents=[], history=False, session_dirs=[]))
        with mock.patch("threading.Thread.start"):
            self.server = serve(watcher, port=0, plugin=self.plugin, token=self.token)
        watcher.projects = {str(self.project): ProjectStatus(root=str(self.project), project="demo")}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def request(self, method, path, body=None, token=TOKEN, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        send = dict(headers or {})
        if body is not None:
            send["Content-Type"] = "application/json"
        if token and method == "POST":
            send[TOKEN_HEADER] = token
        connection.request(method, path, body=None if body is None else json.dumps(body), headers=send)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def env(self, action, **body):
        return self.request("POST", "/api/env/" + action, {"root": str(self.project), "file": ".env", **body})


class HostsRouteTests(Case):
    def test_lists_every_host(self):
        status, payload = self.request("GET", "/api/hosts")
        self.assertEqual(status, 200)
        self.assertEqual(sorted(row["id"] for row in payload["hosts"]), sorted(HOSTS))

    def test_a_foreign_host_header_is_refused(self):
        status, _ = self.request("GET", "/api/hosts", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)


class ProjectOpRouteTests(Case):
    def test_an_op_runs_the_installer_and_needs_the_token(self):
        body = {"root": str(self.project), "op": "hooks-refresh", "dry_run": True}
        status, payload = self.request("POST", "/api/project/op", body, token=None)
        self.assertEqual(status, 403, payload)
        self.assertEqual(self.calls, [])
        status, payload = self.request("POST", "/api/project/op", body)
        self.assertEqual((status, payload["ok"]), (200, True), payload)
        self.assertEqual(self.calls[0][2:], ["--hooks-refresh", "--project", str(self.project), "--dry-run"])

    def test_a_bad_request_is_400_and_a_busy_daemon_is_409(self):
        status, payload = self.request("POST", "/api/project/op", {"root": "/etc", "op": "doctor"})
        self.assertEqual(status, 400, payload)
        self.assertTrue(OP_LOCK.acquire(blocking=False))
        try:
            status, payload = self.request("POST", "/api/project/op", {"root": str(self.project), "op": "doctor"})
        finally:
            OP_LOCK.release()
        self.assertEqual((status, payload["error"]), (409, "operation in progress"))
        self.assertEqual(self.calls, [])


class EnvRouteTests(Case):
    def test_list_reveal_and_save_round_trip(self):
        (self.project / ".env").write_text("API_KEY=old-secret\n", encoding="utf-8")
        status, payload = self.env("list")
        self.assertEqual((status, payload["vars"]), (200, [{"name": "API_KEY", "empty": False}]))
        self.assertNotIn("old-secret", json.dumps(payload))
        self.assertEqual(self.env("reveal", name="API_KEY"), (200, {"value": "old-secret"}))
        changes = [{"name": "API_KEY", "value": "new-secret"}]
        status, payload = self.env("save", changes=changes, dry_run=True)
        self.assertEqual((status, payload), (200, {"written": False, "diff": [{"name": "API_KEY", "change": "change"}]}))
        self.assertEqual((self.project / ".env").read_text(encoding="utf-8"), "API_KEY=old-secret\n")
        status, payload = self.env("save", changes=changes)
        self.assertEqual((status, payload["written"]), (200, True))
        self.assertEqual((self.project / ".env").read_text(encoding="utf-8"), "API_KEY=new-secret\n")

    def test_an_unwatched_root_or_bad_file_is_400_and_reads_nothing(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / ".env").write_text("SECRET=1\n", encoding="utf-8")
        for body in ({"root": str(outside)}, {"file": "../outside/.env"}, {"root": None}):
            with self.subTest(body=body):
                status, payload = self.env("list", **body)
                self.assertEqual(status, 400, payload)
                self.assertNotIn("SECRET", json.dumps(payload))

    def test_no_env_content_without_the_token(self):
        (self.project / ".env").write_text("API_KEY=old-secret\n", encoding="utf-8")
        for action in ("list", "reveal", "save"):
            status, payload = self.request("POST", "/api/env/" + action,
                                           {"root": str(self.project), "file": ".env", "name": "API_KEY",
                                            "changes": [{"name": "A", "value": "1"}]}, token=None)
            self.assertEqual(status, 403, payload)
            self.assertNotIn("API_KEY", json.dumps(payload))
        self.assertEqual((self.project / ".env").read_text(encoding="utf-8"), "API_KEY=old-secret\n")

    def test_there_is_no_get_route_for_env_content(self):
        for action in ("list", "reveal", "save"):
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            connection.request("GET", "/api/env/" + action)
            self.assertEqual(connection.getresponse().status, 404)
            connection.close()


class EnvWithoutTokenDaemonTests(Case):
    """A daemon started without --require-token has no env routes at all."""
    token = None

    def test_every_env_route_is_refused_with_the_reason(self):
        (self.project / ".env").write_text("API_KEY=old-secret\n", encoding="utf-8")
        for action in ("list", "reveal", "save"):
            status, payload = self.env(action, name="API_KEY", changes=[{"name": "A", "value": "1"}])
            self.assertEqual(status, 403, payload)
            self.assertIn("OpenGSD Path app", payload["error"])
            self.assertNotIn("old-secret", json.dumps(payload))
        self.assertEqual((self.project / ".env").read_text(encoding="utf-8"), "API_KEY=old-secret\n")


if __name__ == "__main__":
    unittest.main()
