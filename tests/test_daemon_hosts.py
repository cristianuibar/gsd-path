"""Which coding agents are on this computer, for the app's Agents step and Skills page."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "daemon"))

from gsd_daemon import hosts
from gsd_daemon.plugin import HOSTS, PluginManager


class DetectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.plugin = PluginManager(home=self.home / "daemon", user_home=self.home, environ={})

    def detect(self, on_path=()):
        found = {name: f"/usr/local/bin/{name}" for name in on_path}
        return {row["id"]: row for row in hosts.detect(self.plugin, which=found.get)}

    def test_every_supported_host_is_listed_once_with_its_skills_folder(self):
        rows = self.detect()
        self.assertEqual(sorted(rows), sorted(HOSTS))
        for host, row in rows.items():
            self.assertEqual(row["skills_root"], str(self.plugin.global_root(host)))
            self.assertTrue(row["name"])
            self.assertEqual((row["found"], row["path"]), (False, None))

    def test_a_command_on_path_is_found(self):
        rows = self.detect(on_path=["claude", "cursor-agent", "agy", "kiro-cli"])
        self.assertEqual({host for host, row in rows.items() if row["found"]},
                         {"claude", "cursor", "antigravity", "kiro"})
        self.assertEqual(rows["cursor"]["path"], "/usr/local/bin/cursor-agent")

    def test_a_host_installed_outside_path_is_found_in_its_own_folder(self):
        binary = self.home / ".grok" / "bin" / "grok"
        binary.parent.mkdir(parents=True)
        binary.write_text("")
        rows = self.detect()
        self.assertEqual((rows["grok"]["found"], rows["grok"]["path"]), (True, str(binary)))
        self.assertFalse(rows["kimi"]["found"])

    def test_a_skills_folder_alone_does_not_mean_the_host_is_installed(self):
        (self.home / ".claude" / "skills").mkdir(parents=True)
        self.assertFalse(self.detect()["claude"]["found"])


if __name__ == "__main__":
    unittest.main()
