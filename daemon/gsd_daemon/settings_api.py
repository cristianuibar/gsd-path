"""Settings and diagnostics routes for the native app.

``daemon.json`` is the only store. A write checks every value first, then
applies all of them to the running watcher and saves the file.
"""
from __future__ import annotations

import platform
import sys
from typing import Callable, Dict

from . import __version__
from .config import _abs
from .plugin import STDOUT_TAIL_LINES, _tail
from .sessions import expand_session_dirs

PRICE_KEYS = ("input", "cached", "output")


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _strings(key: str, value) -> list:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{key} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _folders(key: str, value) -> list:
    return [_abs(item) for item in _strings(key, value)]


def _positive(key: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a whole number of 1 or more")
    return value


def _flag(key: str, value) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    return value


def _prices(key: str, value) -> Dict[str, Dict[str, float]]:
    if not isinstance(value, dict):
        raise ValueError("prices must map each model to its prices")
    clean: Dict[str, Dict[str, float]] = {}
    for model, price in value.items():
        if not isinstance(model, str) or not model.strip() or not isinstance(price, dict) or not price:
            raise ValueError("each price entry needs a model name and at least one price")
        for name, amount in price.items():
            if name not in PRICE_KEYS:
                raise ValueError(f"unknown price '{name}' for {model}; use input, cached, output")
            if not _number(amount) or amount < 0:
                raise ValueError(f"the {name} price for {model} must be a number of 0 or more")
        clean[model.strip()] = {name: float(amount) for name, amount in price.items()}
    return clean


CHECKS: Dict[str, Callable] = {
    "parents": _folders, "excludes": _folders, "session_dirs": _strings,
    "max_depth": _positive, "poll_seconds": _positive,
    "notify": _flag, "history": _flag, "prices": _prices,
}


def read_config(handler, _body=None) -> dict:
    return handler.watcher.config.to_dict()


def write_config(handler, body: dict) -> dict:
    unknown = sorted(set(body) - set(CHECKS))
    if unknown:
        raise ValueError(f"unknown setting: {', '.join(unknown)}")
    checked = {key: CHECKS[key](key, value) for key, value in body.items()}
    watcher = handler.watcher
    for key, value in checked.items():
        setattr(watcher.config, key, value)
    # The session index copied these two at start; give it the new values.
    watcher.sessions.dirs = expand_session_dirs(watcher.config.session_dirs)
    watcher.sessions.prices = watcher.config.prices
    watcher.config.save()
    handler.scan()
    return watcher.config.to_dict()


def diagnostics(handler, _body=None) -> dict:
    """A support report the user can copy. It holds settings and log tails, never the write token."""
    logs = {}
    directory = handler.plugin.log_path.parent
    for path in sorted(directory.glob("*.log")) if directory.is_dir() else []:
        try:
            logs[path.name] = _tail(path.read_text(encoding="utf-8", errors="replace"), STDOUT_TAIL_LINES)
        except OSError as error:
            logs[path.name] = f"could not be read: {error}"
    return {
        "daemon_version": __version__,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "platform": platform.platform(),
        "config": handler.watcher.config.to_dict(),
        "projects": len(handler.watcher.projects),
        "plugin": handler._plugin_compact(),
        "logs": logs,
    }
