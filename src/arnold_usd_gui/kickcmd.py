"""Build the kick command line. Does not launch anything."""

from __future__ import annotations

import os
import re
import shlex


def split_flags(text: str) -> list[str]:
    """Split the custom-flag field. Quotes are honored."""
    raw = (text or "").strip()
    if not raw:
        return []
    try:
        return shlex.split(raw, posix=True)
    except ValueError as exc:
        raise ValueError(f"Custom flags: {exc}") from exc


def resolve_output(path: str, scene_path: str) -> str:
    """Absolute render path. Relative paths are next to the USD."""
    raw = (path or "").strip().strip('"')
    if not raw:
        return ""
    if not os.path.isabs(raw):
        raw = os.path.join(os.path.dirname(os.path.abspath(scene_path)), raw)
    return os.path.abspath(raw)


_IMAGE_EXTENSIONS = {".exr", ".png", ".tif", ".tiff", ".jpg", ".jpeg"}


def with_output_extension(path: str, extension: str) -> str:
    """Swap a known image extension, or append one when the name has none."""
    extension = extension if extension.startswith(".") else f".{extension}"
    folder, name = _split_path(path)
    root, ext = os.path.splitext(name)
    if ext.lower() in _IMAGE_EXTENSIONS:
        name = root + extension
    elif not ext:
        name = name + extension
    return _join_path(path, folder, name)


def ensure_frame_token(path: str, width: int = 4) -> str:
    """Insert ``.####`` before the extension when the file name has no ``#``."""
    folder, name = _split_path(path)
    if "#" in name:
        return path
    root, ext = os.path.splitext(name)
    if not ext:
        ext = ".exr"
    name = root + "." + ("#" * max(1, int(width))) + ext
    return _join_path(path, folder, name)


def output_for_frame(path: str, frame: int) -> str:
    """Expand ``#`` runs in the file name. A name without ``#`` is unchanged."""
    folder, name = _split_path(path)
    if "#" not in name:
        return path

    def repl(match: re.Match[str]) -> str:
        return str(int(frame)).zfill(len(match.group(0)))

    return _join_path(path, folder, re.sub(r"#+", repl, name))


def flags_for_renderview(extra: list[str] | None, show: bool) -> list[str]:
    """Match a plain ``kick`` from cmd when the display should open.

    A normal kick shows RenderView and refines progressively. ``-dw`` hides the
    window and ``-dp`` turns that off, so both are removed when showing it.
    """
    if show:
        return [token for token in (extra or []) if token not in ("-dw", "-dp")]
    flags = [token for token in (extra or []) if token != "-dw"]
    flags.append("-dw")
    return flags


def log_path_from_argv(argv: list[str]) -> str:
    """Path after ``-l``, or empty when kick is not writing a log file."""
    for index, token in enumerate(argv[:-1]):
        if token == "-l":
            return argv[index + 1]
    return ""


def with_log_file(argv: list[str], log_path: str) -> list[str]:
    """Append ``-l`` so the GUI can mirror kick's log. Leave an existing ``-l``."""
    if log_path_from_argv(argv):
        return list(argv)
    return [*argv, "-l", log_path]


def build_kick_argv(
    kick: str,
    usd_file: str,
    output: str,
    frame: int,
    camera: str = "",
    extra: list[str] | None = None,
) -> list[str]:
    """Arguments for one frame. Custom flags are appended so they can override."""
    argv = [kick, "-i", usd_file, "-o", output, "-frame", str(int(frame))]
    if camera:
        argv.extend(["-c", camera])
    if extra:
        argv.extend(extra)
    return argv


def format_command(argv: list[str]) -> str:
    return shlex.join(argv)


def _split_path(path: str) -> tuple[str, str]:
    slash = "/" if "/" in path else os.sep
    head, _, tail = path.rpartition(slash)
    if not tail:
        return "", path
    return head, tail


def _join_path(original: str, folder: str, name: str) -> str:
    if not folder:
        return name
    slash = "/" if "/" in original else os.sep
    return folder + slash + name
