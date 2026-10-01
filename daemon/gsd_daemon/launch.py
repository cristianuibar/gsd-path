"""Launch check for the native dashboard app.

The app runs this with the user's Python from its bundled daemon source::

    PYTHONPATH=<bundle>/daemon python3 -B -m gsd_daemon launch --port 8765

It prints one JSON object. The app shows ``problems`` on its setup page. When
``action`` is ``start``, the app starts ``serve_argv`` itself, so it owns that
process and is the only one that stops it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

from . import __version__
from .installer import LAUNCH_AGENT_LABEL, TRAY_APP_NAME, Installer
from .model import SCHEMA
from .plugin import _parse_version

# Same budget the macOS tray app used for /status requests (StatusClient.swift).
STATUS_TIMEOUT_S = 3.0
# Written once legacy autostart is proven gone, so later launches skip the
# check (and the macOS System Events prompt it can trigger).
RETIRED_MARKER = Path("app") / "legacy-autostart-retired"
# How the daemon is started: `python -m gsd_daemon ...` or the `gsd-path-daemon` script.
DAEMON_COMMAND = re.compile(r"(?:^|\s)-m\s+gsd_daemon(?:\s|$)|(?:^|[\s/\\])gsd-path-daemon(?:\.exe)?(?:\s|$)")


def _problem(kind: str, message: str, fix: str, blocking: bool = True, detail: Optional[dict] = None) -> dict:
    problem = {"kind": kind, "message": message, "fix": fix, "blocking": blocking}
    if detail is not None:
        problem["detail"] = detail
    return problem


def probe_port(port: int) -> dict:
    """What holds the port: ``free``, a GSD Path ``daemon``, or ``other``."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status",
                                    timeout=STATUS_TIMEOUT_S) as response:
            payload = json.loads(response.read())
    except urllib.error.URLError as error:
        if isinstance(error.reason, ConnectionRefusedError):
            return {"state": "free"}
        return {"state": "other"}
    except ConnectionRefusedError:
        return {"state": "free"}
    except (OSError, ValueError):
        return {"state": "other"}
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return {"state": "other"}
    daemon = payload.get("daemon") if isinstance(payload.get("daemon"), dict) else {}
    pid = daemon.get("pid")
    return {"state": "daemon", "version": daemon.get("version"),
            "pid": pid if isinstance(pid, int) else None}


# -- legacy autostart ---------------------------------------------------------

def legacy_registrations(installer: Installer, check_login_item: bool) -> List[str]:
    """Autostart entries left by `gsd_daemon install` or the Swift tray app."""
    run = installer.runner.run
    found = []
    if installer.platform == "darwin":
        service = f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"
        if installer.plist_path.exists() or run(["launchctl", "print", service], check=False).returncode == 0:
            found.append("launch-agent")
        if installer.app_dest.exists():
            found.append("tray-app")
        if check_login_item:
            items = run(["osascript", "-e",
                         'tell application "System Events" to get the name of every login item'],
                        check=False)
            if items.returncode != 0:
                found.append("login-item-unknown")
            elif TRAY_APP_NAME in [name.strip() for name in items.stdout.split(",")]:
                found.append("login-item")
    elif installer.platform == "win32":
        if installer.shortcut_path.exists():
            found.append("startup-shortcut")
    else:
        enabled = (installer.runner.which("systemctl") is not None and
                   run(["systemctl", "--user", "is-enabled", installer.unit_path.name],
                       check=False).returncode == 0)
        if installer.unit_path.exists() or enabled:
            found.append("systemd-unit")
    return found


def manual_fix(name: str, installer: Installer) -> str:
    fixes = {
        "launch-agent": (f"Run `launchctl bootout gui/{os.getuid() if hasattr(os, 'getuid') else 0}/"
                         f"{LAUNCH_AGENT_LABEL}`, then delete {installer.plist_path}."),
        "tray-app": f"Quit GSDPathTray and delete {installer.app_dest}.",
        "login-item": f"Remove {TRAY_APP_NAME} in System Settings > General > Login Items.",
        "login-item-unknown": (f"Allow GSD Path to control System Events, or check System Settings > "
                               f"General > Login Items and remove {TRAY_APP_NAME}."),
        "startup-shortcut": f"Delete {installer.shortcut_path}.",
        "systemd-unit": (f"Run `systemctl --user disable --now {installer.unit_path.name}`, "
                         f"then delete {installer.unit_path}."),
    }
    return fixes[name]


def retire_legacy(installer: Installer, seen: Optional[List[str]] = None) -> List[str]:
    """Remove old autostart with the existing uninstall; return what remains.

    The uninstall exit status is not trusted: every entry is checked again.
    `seen` receives every entry found before the removal.
    """
    marker = installer.gsd_home / RETIRED_MARKER
    if marker.exists():
        return []
    # Only a machine that ran `gsd_daemon install` can have the old login item.
    check_login_item = installer.venv_dir.exists()
    found = legacy_registrations(installer, check_login_item)
    if seen is not None:
        seen.extend(found)
    if found:
        failure = None
        try:
            installer.uninstall()
        except (subprocess.CalledProcessError, OSError) as error:
            failure = error
        found = legacy_registrations(installer, check_login_item)
        if failure is not None and not found:
            raise failure
    if not found:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(__version__ + "\n", encoding="utf-8")
    return found


# -- running daemon -----------------------------------------------------------

def listener_pid(port: int, installer: Installer) -> Optional[int]:
    """PID of the process listening on 127.0.0.1:<port>, when the OS says."""
    run = installer.runner.run
    if installer.platform == "win32":
        output = run(["netstat", "-ano", "-p", "TCP"], check=False).stdout
        for line in output.splitlines():
            parts = line.split()
            if len(parts) == 5 and parts[1] == f"127.0.0.1:{port}" and parts[3] == "LISTENING":
                return int(parts[4])
        return None
    if installer.runner.which("lsof"):
        output = run(["lsof", "-nP", f"-iTCP@127.0.0.1:{port}", "-sTCP:LISTEN", "-t"], check=False).stdout
        pids = [int(line) for line in output.split() if line.isdigit()]
        return pids[0] if pids else None
    if installer.runner.which("ss"):
        output = run(["ss", "-ltnpH", f"sport = :{port}"], check=False).stdout
        for part in output.replace(",", " ").split():
            if part.startswith("pid=") and part[4:].isdigit():
                return int(part[4:])
    return None


def process_command(pid: int, installer: Installer) -> str:
    if installer.platform == "win32":
        argv = ["powershell", "-NoProfile", "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"]
    else:
        argv = ["ps", "-o", "command=", "-p", str(pid)]
    return installer.runner.run(argv, check=False).stdout.strip()


def stop_daemon(port: int, reported_pid: Optional[int], installer: Installer) -> Optional[int]:
    """Stop a GSD Path daemon on the port. Returns the PID it could not stop, or None."""
    pid = reported_pid or listener_pid(port, installer)
    if pid is None:
        return -1
    command = process_command(pid, installer)
    if not DAEMON_COMMAND.search(command):
        return pid
    if installer.platform == "win32":
        installer.runner.run(["taskkill", "/PID", str(pid), "/F"], check=False)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + STATUS_TIMEOUT_S
    while time.monotonic() < deadline:
        if probe_port(port)["state"] == "free":
            return None
        time.sleep(0.1)
    return pid


# -- venv ----------------------------------------------------------------------

def port_owner(port: int, installer: Installer, pid: Optional[int] = None) -> dict:
    """Who holds the port, for the app's "port in use" screen. Best effort."""
    if pid is None or pid < 0:
        pid = listener_pid(port, installer)
    return {"pid": pid, "command": process_command(pid, installer) or None if pid else None}


def installed_version(installer: Installer) -> Optional[str]:
    if not installer.venv_python.exists():
        return None
    result = installer.runner.run(
        [str(installer.venv_python), "-c",
         "import importlib.metadata as m; print(m.version('gsd-path-daemon'))"], check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def ensure_venv(installer: Installer) -> str:
    """Install the bundled daemon unless the venv already has this or a newer one."""
    current = installed_version(installer)
    current_parts = _parse_version(current)
    if current_parts is not None and current_parts >= _parse_version(__version__):
        return current
    source = installer.package_dir
    with tempfile.TemporaryDirectory(prefix="gsd-path-daemon-") as work:
        # pip builds a local package in place; build a copy, never the app bundle.
        copy = Path(work) / "daemon"
        shutil.copytree(source / "gsd_daemon", copy / "gsd_daemon",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("pyproject.toml", "README.md"):
            shutil.copy2(source / name, copy / name)
        # A bundle without write bits gives a copy that pip cannot delete from its build directory.
        for path in (copy, *copy.rglob("*")):
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        installer.repo_root = Path(work)
        try:
            code = installer.install(no_tray=True, no_autostart=True)
        finally:
            installer.repo_root = source.parent
    if code != 0:
        raise OSError(f"`gsd_daemon install` failed with exit code {code}.")
    return __version__


# -- launch ------------------------------------------------------------------------

def git_fix(platform: str) -> str:
    if platform == "darwin":
        return "Run `xcode-select --install`, or install Git from https://git-scm.com/download/mac."
    if platform == "win32":
        return "Install Git for Windows from https://git-scm.com/download/win."
    return "Install git with your package manager, for example `sudo apt install git`."


def _requirement(name: str, required: bool, state: str, detail: Optional[str] = None) -> dict:
    return {"id": name, "required": required, "state": state, "detail": detail}


def requirements(installer: Installer) -> List[dict]:
    """What the app's Requirements step shows. Facts only; the app owns the wording."""
    runner = installer.runner
    rows = [_requirement("python", True, "ready", ".".join(str(part) for part in sys.version_info[:3]))]
    git = runner.run(["git", "--version"], check=False) if runner.which("git") else None
    if git is None or git.returncode != 0:
        rows.append(_requirement("git", True, "missing"))
    else:
        # '2.39.5 (Apple Git-154)': the first line without the leading words.
        found = re.search(r"\d.*", (git.stdout or "").partition("\n")[0])
        rows.append(_requirement("git", True, "ready", found.group(0).strip() if found else None))
    if installer.platform not in ("darwin", "win32"):
        # Debian and Ubuntu ship venv apart from Python; without it the daemon venv cannot be made.
        venv = (installer.venv_pip.exists() or
                runner.run([sys.executable, "-c", "import ensurepip"], check=False).returncode == 0)
        rows.append(_requirement("python-venv", True, "ready" if venv else "missing"))
    if runner.which("gh") is None:
        rows.append(_requirement("gh", False, "missing"))
    else:
        signed_in = runner.run(["gh", "auth", "token"], check=False).returncode == 0
        rows.append(_requirement("gh", False, "ready" if signed_in else "signed-out"))
    return rows


def launch(port: int, installer: Installer) -> dict:
    result = {"action": "setup", "port": port, "url": f"http://127.0.0.1:{port}/",
              "version": None, "serve_argv": None, "autostart_ok": True, "problems": [],
              "requirements": [], "legacy": [], "replaced": None}
    try:
        _check(port, installer, result)
    except (subprocess.CalledProcessError, OSError) as error:
        result["problems"].append(_problem(
            "launch", f"The launch check failed: {error}", "Correct this error, then choose Retry."))
    return result


def _check(port: int, installer: Installer, result: dict) -> None:
    problems = result["problems"]
    result["requirements"] = requirements(installer)
    missing = [row["id"] for row in result["requirements"] if row["required"] and row["state"] == "missing"]

    if "git" in missing:
        problems.append(_problem("git", "Git is not installed.", git_fix(installer.platform)))
    if "python-venv" in missing:
        problems.append(_problem(
            "python-venv", "The Python venv module is not installed.",
            "Run `sudo apt install python3-venv` (`python3 -m venv` needs it), then choose Retry."))

    seen: List[str] = []
    remaining = retire_legacy(installer, seen)
    # What the app's "Moving to the new app" screen lists: every old entry and whether it is gone.
    result["legacy"] = [{"name": name, "removed": name not in remaining, "fix": manual_fix(name, installer)}
                        for name in seen + [name for name in remaining if name not in seen]]
    if remaining:
        result["autostart_ok"] = False
        for name in remaining:
            problems.append(_problem(
                "autostart", f"An old GSD Path autostart entry is still present ({name}).",
                manual_fix(name, installer), blocking=False))

    holder = probe_port(port)
    if holder["state"] == "other":
        problems.append(_problem(
            "port", f"Another program is using port {port}.",
            f"Quit the program that uses port {port}, then choose Retry.",
            detail=port_owner(port, installer)))
    if any(problem["blocking"] for problem in problems):
        return

    try:
        version = ensure_venv(installer)
    except (subprocess.CalledProcessError, OSError) as error:
        detail = (getattr(error, "stderr", None) or str(error)).strip().splitlines()[-1:]
        problems.append(_problem(
            "install", f"The daemon could not be installed into {installer.venv_dir}.",
            "Check your network connection (pip downloads the daemon's dependencies), "
            f"then choose Retry. {' '.join(detail)}".strip()))
        return
    result["version"] = version

    if holder["state"] == "daemon":
        running = _parse_version(holder.get("version"))
        if running is not None and running >= _parse_version(version):
            result["action"] = "reuse"
            result["version"] = holder["version"]
            return
        stuck = stop_daemon(port, holder.get("pid"), installer)
        if stuck is not None:
            who = "An older GSD Path daemon" if stuck != -1 else "A program"
            problems.append(_problem(
                "port", f"{who} is using port {port} and could not be stopped.",
                "Stop it (Activity Monitor, Task Manager, or `kill`), then choose Retry.",
                detail=port_owner(port, installer, stuck)))
            return
        result["replaced"] = holder.get("version") or "unknown"

    result["action"] = "start"
    result["serve_argv"] = [str(installer.venv_python), "-m", "gsd_daemon", "serve", "--port", str(port),
                            "--require-token"]
