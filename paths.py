"""Locations that stay valid both as a script and as a frozen installer build."""

import os
import sys


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def resource_dir():
    """Read-only files shipped with the app (icon)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def downloads_dir():
    """Writable cache for downloaded driver packages.

    Source runs keep using ./downloads. An installed exe must not write into
    Program Files, so it uses %LOCALAPPDATA%\\Driver Finder\\downloads.
    """
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "Driver Finder", "downloads")
    else:
        path = os.path.join(resource_dir(), "downloads")
    os.makedirs(path, exist_ok=True)
    return path


def data_dir():
    """Per-user writable root shared by every feature."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "Driver Finder")
    os.makedirs(path, exist_ok=True)
    return path


def backups_dir():
    """Driver backups and offline packs live here, newest first on read."""
    path = os.path.join(data_dir(), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def cache_dir():
    """Small on-disk cache that survives restarts (catalog query results)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "Driver Finder", "cache")
    os.makedirs(path, exist_ok=True)
    return path
