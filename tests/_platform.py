"""Platform capability guards and fakes shared by the test suite.

Import as ``from tests._platform import ...`` (or ``import _platform`` when the
tests directory is on sys.path).
"""

from __future__ import annotations

import functools
import os
import sys
import tempfile
import unittest
from pathlib import Path

WINDOWS = os.name == "nt"


@functools.lru_cache(maxsize=None)
def can_symlink() -> bool:
    """Whether this process may create symlinks (Windows needs Developer Mode or admin)."""
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "target"
        target.write_bytes("".encode("utf-8"))
        try:
            (Path(directory) / "link").symlink_to(target)
        except (OSError, NotImplementedError):
            return False
    return True


requires_symlink = unittest.skipUnless(can_symlink(), "symlinks unavailable on this host")

# chmod-based denial (0, 0o555, exec bits) has no effect on Windows ACLs.
posix_permissions_only = unittest.skipIf(WINDOWS, "POSIX permission bits are not enforced on Windows")

posix_only = unittest.skipIf(WINDOWS, "POSIX-only behavior")
windows_only = unittest.skipUnless(WINDOWS, "Windows-only behavior")


@functools.lru_cache(maxsize=None)
def _bash_available() -> bool:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        import _common

        _common.find_bash()
    except Exception:
        return False
    return True


requires_bash = unittest.skipUnless(_bash_available(), "no usable bash on this host")


def fake_cli(bin_dir: Path, name: str, python_source: str) -> Path:
    """Write an executable named name in bin_dir that runs python_source.

    POSIX gets a shebang script; Windows gets name.py plus a name.cmd shim, which
    PATHEXT resolution finds. Put bin_dir first on PATH to use it.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    if not WINDOWS:
        path = bin_dir / name
        path.write_bytes(f"#!{sys.executable}\n{python_source}".encode("utf-8"))
        path.chmod(0o755)
        return path
    body = bin_dir / f"{name}.py"
    body.write_bytes(python_source.encode("utf-8"))
    shim = bin_dir / f"{name}.cmd"
    shim.write_bytes(f'@"{sys.executable}" "%~dp0{name}.py" %*\r\n'.encode("utf-8"))
    return shim
