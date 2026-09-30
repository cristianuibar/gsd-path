"""Subprocess helpers for daemon code (hide console windows on Windows)."""
from __future__ import annotations

import subprocess
import sys
from typing import Any, Mapping, Optional, Sequence

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

TOAST_APP_ID = "OpenGSD.GSDPath.Daemon"


def _win_creationflags(extra: int = 0) -> int:
    if sys.platform != "win32":
        return extra
    return CREATE_NO_WINDOW | extra


def run(
    args: Sequence[str],
    *,
    input: Optional[str] = None,
    capture_output: bool = False,
    text: bool = False,
    timeout: Optional[float] = None,
    check: bool = False,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", _win_creationflags())
    return subprocess.run(
        args,
        input=input,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        check=check,
        env=env,
        cwd=cwd,
        **kwargs,
    )


def popen(args: Sequence[str], **kwargs: Any) -> subprocess.Popen:
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", _win_creationflags())
    return subprocess.Popen(args, **kwargs)
