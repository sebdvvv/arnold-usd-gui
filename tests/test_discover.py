from __future__ import annotations

import os

from arnold_usd_gui.config import AppConfig, load_config, save_config
from arnold_usd_gui.discover import arnold_root_from_kick, discover_kick


def _touch(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb"):
        pass
    return path


def test_discover_arnold_root_then_path(tmp_path):
    root = tmp_path / "Arnold"
    kick = _touch(str(root / "bin" / "kick.exe"))
    other = tmp_path / "dist" / "Arnold"
    other_kick = _touch(str(other / "kick.exe"))
    unrelated = tmp_path / "tools"
    _touch(str(unrelated / "kick.exe"))

    found, how = discover_kick(
        environ={"ARNOLD_ROOT": str(root), "PATH": str(unrelated)},
        exe_name="kick.exe",
    )
    assert os.path.normcase(found) == os.path.normcase(kick)
    assert how == "ARNOLD_ROOT"

    found, how = discover_kick(
        environ={"PATH": os.pathsep.join([str(unrelated), str(other)])},
        exe_name="kick.exe",
    )
    assert os.path.normcase(found) == os.path.normcase(other_kick)
    assert how == "PATH"

    found, how = discover_kick(
        environ={"PATH": str(root)},
        exe_name="kick.exe",
    )
    assert os.path.normcase(found) == os.path.normcase(kick)
    assert how == "PATH"

    found, how = discover_kick(
        environ={"PATH": str(unrelated)},
        exe_name="kick.exe",
    )
    assert found == ""
    assert how == ""


def test_configured_executable_wins(tmp_path):
    root = tmp_path / "Arnold"
    _touch(str(root / "bin" / "kick.exe"))
    chosen = _touch(str(tmp_path / "custom" / "kick.exe"))
    found, how = discover_kick(
        environ={"ARNOLD_ROOT": str(root)},
        configured_kick=chosen,
        exe_name="kick.exe",
    )
    assert os.path.normcase(found) == os.path.normcase(chosen)
    assert how == "executable"

    found, how = discover_kick(
        environ={},
        configured_root=str(root),
        exe_name="kick.exe",
    )
    assert how == "ARNOLD_ROOT setting"
    assert found.endswith("kick.exe")


def test_root_from_kick_path():
    assert os.path.basename(arnold_root_from_kick(r"D:\Arnold\bin\kick.exe")) == "Arnold"
    assert arnold_root_from_kick(r"D:\tools\kick.exe") == ""


def test_config_roundtrip(tmp_path, monkeypatch):
    dest = tmp_path / "settings.json"
    monkeypatch.setenv("ARNOLD_USD_GUI_CONFIG", str(dest))
    save_config(
        AppConfig(
            kick_executable=r"D:\Arnold\bin\kick.exe",
            arnold_root=r"D:\Arnold",
            custom_flags="-v 3",
        )
    )
    loaded = load_config()
    assert loaded.kick_executable == r"D:\Arnold\bin\kick.exe"
    assert loaded.arnold_root == r"D:\Arnold"
    assert loaded.flags == "-v 3"

    dest.write_text("{", encoding="utf-8")
    assert load_config().kick_executable == ""
    assert load_config().flags.startswith("-dw")
