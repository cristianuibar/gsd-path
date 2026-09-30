import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "daemon"))

from gsd_daemon import subprocess_platform
from gsd_daemon import sessions
from gsd_daemon.installer import Installer


class PsQuotingTests(unittest.TestCase):
    def test_single_quoted_path_doubles_embedded_apostrophe(self):
        path = Path("/Users/o'brien/.gsd-path/venv/Scripts/pythonw.exe")
        quoted = Installer._ps_single_quoted(path)
        self.assertEqual(quoted, "'/Users/o''brien/.gsd-path/venv/Scripts/pythonw.exe'")


class SessionPathTests(unittest.TestCase):
    def test_path_under_root_uses_normcase_on_windows(self):
        with mock.patch("gsd_daemon.sessions.os.name", "nt"), mock.patch(
            "gsd_daemon.sessions.os.sep", "\\"
        ), mock.patch("gsd_daemon.sessions.os.path.normcase", side_effect=str.lower):
            self.assertTrue(
                sessions.SessionIndex._path_under_root(
                    r"C:\Repo\Sub", r"C:\repo"
                )
            )
            self.assertFalse(
                sessions.SessionIndex._path_under_root(
                    r"C:\Other", r"C:\repo"
                )
            )

    def test_default_session_dirs_include_windows_orca_glob(self):
        joined = " ".join(sessions.DEFAULT_SESSION_DIRS)
        self.assertIn("AppData/Roaming/orca", joined)


class SubprocessPlatformTests(unittest.TestCase):
    def test_toast_app_id_is_stable(self):
        self.assertEqual(subprocess_platform.TOAST_APP_ID, "OpenGSD.GSDPath.Daemon")

    def test_run_adds_create_no_window_on_win32(self):
        with mock.patch.object(sys, "platform", "win32"):
            with mock.patch("gsd_daemon.subprocess_platform.subprocess.run") as run:
                run.return_value = mock.Mock(returncode=0)
                subprocess_platform.run(["echo", "hi"], capture_output=True)
                _args, kwargs = run.call_args
                self.assertEqual(
                    kwargs.get("creationflags"),
                    subprocess_platform.CREATE_NO_WINDOW,
                )


class ToastInstallScriptTests(unittest.TestCase):
    def test_toast_registration_script_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            installer = Installer(
                home=home,
                launch_agents_dir=home / "Library" / "LaunchAgents",
                startup_dir=home / "startup",
                systemd_user_dir=home / "systemd",
                runner=mock.Mock(),
                platform="win32",
                repo_root=Path(tmp) / "repo",
            )
            script = installer.windows_toast_registration_script()
            self.assertIn(subprocess_platform.TOAST_APP_ID, script)
            self.assertIn("AppUserModelId", script)
            self.assertIn("GSD Path Daemon.lnk", script)


if __name__ == "__main__":
    unittest.main()
