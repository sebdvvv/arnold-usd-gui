"""Frame lists for stills, ranges, comma lists, and FML."""

from __future__ import annotations

import re

_FRAME_RE = re.compile(r"^(-?\d+)(?:\s*-\s*(-?\d+))?$")


def parse_frames(text: str) -> list[int]:
    """Parse ``1, 5, 10-12`` into a unique frame list, order preserved.

    A range is inclusive. ``10-8`` walks downward. Repeated frames are dropped.
    """
    if text is None or not str(text).strip():
        raise ValueError("No frames. Use 1, 5, 10 or 1-10.")
    frames: list[int] = []
    seen: set[int] = set()
    for part in str(text).split(","):
        token = part.strip()
        if not token:
            continue
        match = _FRAME_RE.match(token)
        if match is None:
            raise ValueError(
                f"Cannot read frame '{token}'. Use 1, 5, 10 or 1-10."
            )
        start = int(match.group(1))
        end_text = match.group(2)
        if end_text is None:
            sequence = [start]
        else:
            end = int(end_text)
            step = 1 if end >= start else -1
            sequence = list(range(start, end + step, step))
        for frame in sequence:
            if frame in seen:
                continue
            seen.add(frame)
            frames.append(frame)
    if not frames:
        raise ValueError("No frames. Use 1, 5, 10 or 1-10.")
    return frames


def frames_from_range(start: int, end: int, step: int = 1) -> list[int]:
    """Inclusive integer range. Step is always positive."""
    start_i = int(start)
    end_i = int(end)
    step_i = abs(int(step)) or 1
    if end_i < start_i:
        start_i, end_i = end_i, start_i
    return list(range(start_i, end_i + 1, step_i))


def fml(start: int, end: int) -> list[int]:
    """First, middle, and last frame of an inclusive range."""
    start_i = int(start)
    end_i = int(end)
    if end_i < start_i:
        start_i, end_i = end_i, start_i
    middle = start_i + (end_i - start_i) // 2
    return parse_frames(", ".join(str(frame) for frame in (start_i, middle, end_i)))


def format_frames(frames: list[int]) -> str:
    return ", ".join(str(frame) for frame in frames)
