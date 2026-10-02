from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

from . import subprocess_platform


def pick_folder() -> Optional[str]:
    try:
        if sys.platform == "darwin":
            result = subprocess_platform.run(
                ["osascript", "-e", "POSIX path of (choose folder)"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                return None
            return _clean(result.stdout)
        if sys.platform == "win32":
            script = (
                "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "if ($dialog.ShowDialog() -eq 'OK') { $dialog.SelectedPath }"
            )
            result = subprocess_platform.run(
                ["powershell", "-NoProfile", "-STA", "-Command", script],
                capture_output=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                return None
            text = result.stdout.decode("utf-8", errors="replace")
            return _clean(text)
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _clean(output: str) -> Optional[str]:
    path = output.strip().rstrip("/\\")
    if not path:
        return None
    return os.path.abspath(os.path.expanduser(path))
