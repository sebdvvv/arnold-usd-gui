"""arnold-usd-gui — kick Arnold from a USD stage.

Launch::

    python -m arnold_usd_gui
    python -m arnold_usd_gui path/to/file.usda
"""

from __future__ import annotations

__version__ = "0.1.0"

APP_NAME = "Arnold USD (GUI)"
APP_AUTHOR = "Sébastien Durand"
APP_YEAR = "2026"
APP_LICENSE = "MIT License"

__all__ = [
    "APP_AUTHOR",
    "APP_LICENSE",
    "APP_NAME",
    "APP_YEAR",
    "__version__",
    "main",
]


def main(argv: list[str] | None = None) -> int:
    """Launch the Qt UI."""
    import sys

    try:
        from arnold_usd_gui.ui import main as ui_main
    except ImportError as exc:
        text = str(exc)
        print(text, file=sys.stderr)
        _report_startup_error(text)
        return 1
    return int(ui_main(argv) or 0)


def _report_startup_error(text: str) -> None:
    """Show a dialog when pythonw has no console."""
    import os

    try:
        from PySide6 import QtWidgets  # type: ignore
    except ImportError:
        try:
            from PySide2 import QtWidgets  # type: ignore
        except ImportError:
            QtWidgets = None  # type: ignore
    if QtWidgets is not None:
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        QtWidgets.QMessageBox.critical(None, APP_NAME, text)
        return
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, APP_NAME, 0x10)
