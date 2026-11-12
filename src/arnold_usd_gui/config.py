"""User settings for kick location and custom flags."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

DEFAULT_CUSTOM_FLAGS = "-dw -dp -nokeypress -v 2"


@dataclass
class AppConfig:
    kick_executable: str = ""
    arnold_root: str = ""
    # None means "never saved" — the UI shows DEFAULT_CUSTOM_FLAGS.
    custom_flags: str | None = None
    show_renderview: bool = True
    image_format: str = "exr"
    bit_depth: str = "half"
    subdiv_override: bool = False
    subdiv_catmull: bool = True
    subdiv_iterations: int = 2
    subdiv_scope: str = "existing"

    @property
    def flags(self) -> str:
        if self.custom_flags is None:
            return DEFAULT_CUSTOM_FLAGS
        return self.custom_flags


def config_file() -> str:
    override = os.environ.get("ARNOLD_USD_GUI_CONFIG", "").strip()
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
    return os.path.join(base, "arnold-usd-gui", "settings.json")


def load_config() -> AppConfig:
    path = config_file()
    if not os.path.isfile(path):
        return AppConfig()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return AppConfig()
    if not isinstance(data, dict):
        return AppConfig()
    flags = data.get("custom_flags", None)
    if flags is not None and not isinstance(flags, str):
        flags = None
    return AppConfig(
        kick_executable=_text(data.get("kick_executable")),
        arnold_root=_text(data.get("arnold_root")),
        custom_flags=flags,
        show_renderview=_as_bool(data.get("show_renderview"), True),
        image_format=_text(data.get("image_format")) or "exr",
        bit_depth=_text(data.get("bit_depth")) or "half",
        subdiv_override=_as_bool(data.get("subdiv_override"), False),
        subdiv_catmull=_as_bool(data.get("subdiv_catmull"), True),
        subdiv_iterations=max(0, _int(data.get("subdiv_iterations"), 2)),
        subdiv_scope=_scope(data.get("subdiv_scope")),
    )


def save_config(config: AppConfig) -> str:
    path = config_file()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {
        "kick_executable": config.kick_executable or "",
        "arnold_root": config.arnold_root or "",
        "custom_flags": config.flags if config.custom_flags is None else config.custom_flags,
        "show_renderview": bool(config.show_renderview),
        "image_format": config.image_format or "exr",
        "bit_depth": config.bit_depth or "half",
        "subdiv_override": bool(config.subdiv_override),
        "subdiv_catmull": bool(config.subdiv_catmull),
        "subdiv_iterations": max(0, int(config.subdiv_iterations)),
        "subdiv_scope": _scope(config.subdiv_scope),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    return ""


def _int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _scope(value: object) -> str:
    text = value if isinstance(value, str) else ""
    return text if text in {"existing", "all"} else "existing"


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return bool(value)
