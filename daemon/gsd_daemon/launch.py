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
import signal
import subprocess
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


def _problem(kind: str, message: str, fix: str, blocking: bool = True) -> dict:
    return {"kind": kind, "message": message, "fix": fix, "blocking": blocking}


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


def retire_legacy(installer: Installer) -> List[str]:
    """Remove old autostart with the existing uninstall; return what remains.

    The uninstall exit status is not trusted: every entry is checked again.
    """
    marker = installer.gsd_home / RETIRED_MARKER
    if marker.exists():
        return []
    # Only a machine that ran `gsd_daemon install` can have the old login item.
    check_login_item = installer.venv_dir.exists()
    found = legacy_registrations(installer, check_login_item)
    if found:
        installer.uninstall()
        found = legacy_registrations(installer, check_login_item)
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
    installer.install(no_tray=True, no_autostart=True)
    return __version__


# -- launch ------------------------------------------------------------------------

def git_fix(platform: str) -> str:
    if platform == "darwin":
        return "Run `xcode-select --install`, or install Git from https://git-scm.com/download/mac."
    if platform == "win32":
        return "Install Git for Windows from https://git-scm.com/download/win."
    return "Install git with your package manager, for example `sudo apt install git`."


def launch(port: int, installer: Installer) -> dict:
    result = {"action": "setup", "port": port, "url": f"http://127.0.0.1:{port}/",
              "version": None, "serve_argv": None, "autostart_ok": True, "problems": []}
    problems = result["problems"]

    if installer.runner.which("git") is None:
        problems.append(_problem("git", "Git is not installed.", git_fix(installer.platform)))

    remaining = retire_legacy(installer)
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
            f"Quit the program that uses port {port}, then choose Retry."))
    if any(problem["blocking"] for problem in problems):
        return result

    try:
        version = ensure_venv(installer)
    except (subprocess.CalledProcessError, OSError) as error:
        detail = (getattr(error, "stderr", None) or str(error)).strip().splitlines()[-1:]
        problems.append(_problem(
            "install", f"The daemon could not be installed into {installer.venv_dir}.",
            "Check your network connection (pip downloads the daemon's dependencies), "
            f"then choose Retry. {' '.join(detail)}".strip()))
        return result
    result["version"] = version

    if holder["state"] == "daemon":
        running = _parse_version(holder.get("version"))
        if running is not None and running >= _parse_version(version):
            result["action"] = "reuse"
            result["version"] = holder["version"]
            return result
        stuck = stop_daemon(port, holder.get("pid"), installer)
        if stuck is not None:
            who = "An older GSD Path daemon" if stuck != -1 else "A program"
            problems.append(_problem(
                "port", f"{who} is using port {port} and could not be stopped.",
                "Stop it (Activity Monitor, Task Manager, or `kill`), then choose Retry."))
            return result

    result["action"] = "start"
    result["serve_argv"] = [str(installer.venv_python), "-m", "gsd_daemon", "serve", "--port", str(port)]
    return result
