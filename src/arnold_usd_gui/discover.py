"""Locate the Arnold kick executable."""

from __future__ import annotations

import os
import re

_ARNOLD_COMPONENT = re.compile(r"^arnold([^a-z].*)?$")


def kick_executable_name() -> str:
    return "kick.exe" if os.name == "nt" else "kick"


def discover_kick(
    environ: dict[str, str] | None = None,
    configured_kick: str = "",
    configured_root: str = "",
    exe_name: str | None = None,
) -> tuple[str, str]:
    """Return ``(kick_path, how)``. ``how`` is empty when nothing was found.

    Order:

    1. Saved executable, when that file exists.
    2. Saved ARNOLD_ROOT → ``ARNOLD_ROOT/bin/<kick>`` (or ``<kick>`` in the root).
    3. The ``ARNOLD_ROOT`` environment variable, same layout.
    4. A PATH entry with an ``Arnold`` or ``Arnold-<version>`` folder that holds
       ``kick`` or ``bin/kick``.
    """
    env = os.environ if environ is None else environ
    exe = exe_name or kick_executable_name()

    configured = (configured_kick or "").strip().strip('"')
    if configured and os.path.isfile(configured):
        return os.path.abspath(configured), "executable"

    root = (configured_root or "").strip().strip('"')
    if root:
        found = _find_in(root, exe)
        if found:
            return found, "ARNOLD_ROOT setting"

    env_root = (env.get("ARNOLD_ROOT") or "").strip().strip('"')
    if env_root:
        found = _find_in(env_root, exe)
        if found:
            return found, "ARNOLD_ROOT"

    for entry in (env.get("PATH") or "").split(os.pathsep):
        folder = entry.strip().strip('"')
        if not folder or not _path_has_arnold_folder(folder):
            continue
        found = _find_in(folder, exe)
        if found:
            return found, "PATH"
    return "", ""


def _path_has_arnold_folder(path: str) -> bool:
    """True when a path component is ``Arnold`` or ``Arnold-<version>``."""
    for part in re.split(r"[\\/]", path):
        if _ARNOLD_COMPONENT.match(part.strip().lower()):
            return True
    return False


def arnold_root_from_kick(kick_path: str) -> str:
    """Parent of ``bin`` when kick lives in an Arnold ``bin`` directory."""
    if not kick_path:
        return ""
    folder = os.path.dirname(os.path.abspath(kick_path))
    if os.path.basename(folder).lower() == "bin":
        return os.path.dirname(folder)
    return ""


def _find_in(directory: str, exe_name: str) -> str:
    if not directory or not os.path.isdir(directory):
        return ""
    direct = os.path.join(directory, exe_name)
    nested = os.path.join(directory, "bin", exe_name)
    if os.path.isfile(direct):
        return os.path.abspath(direct)
    if os.path.isfile(nested):
        return os.path.abspath(nested)
    return ""
