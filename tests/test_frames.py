from __future__ import annotations

import pytest

from arnold_usd_gui.frames import fml, format_frames, frames_from_range, parse_frames
from arnold_usd_gui.kickcmd import (
    build_kick_argv,
    ensure_frame_token,
    with_output_extension,
    flags_for_renderview,
    log_path_from_argv,
    output_for_frame,
    resolve_output,
    split_flags,
    with_log_file,
)
from arnold_usd_gui.values import parse_option_text


def test_parse_frames_commas_and_ranges():
    assert parse_frames("1, 2, 10-12") == [1, 2, 10, 11, 12]
    assert parse_frames("1, 1, 2") == [1, 2]
    assert parse_frames("10-8") == [10, 9, 8]
    assert parse_frames("-2-1") == [-2, -1, 0, 1]


def test_parse_frames_rejects_junk():
    with pytest.raises(ValueError):
        parse_frames("1, a")
    with pytest.raises(ValueError):
        parse_frames("   ")


def test_fml_and_range():
    assert fml(1, 10) == [1, 5, 10]
    assert fml(1, 2) == [1, 2]
    assert fml(10, 1) == [1, 5, 10]
    assert frames_from_range(1, 10, 2) == [1, 3, 5, 7, 9]
    assert format_frames([1, 5, 10]) == "1, 5, 10"


def test_with_output_extension_swaps_known_types():
    assert with_output_extension("D:/renders/shot.####.exr", ".png") == "D:/renders/shot.####.png"
    assert with_output_extension("D:/renders/shot", ".tif").endswith("shot.tif")
    assert with_output_extension("D:/renders/shot.jpg", "exr").endswith("shot.exr")


def test_output_tokens():
    token = ensure_frame_token("D:/renders/shot.exr")
    assert token == "D:/renders/shot.####.exr"
    assert output_for_frame(token, 12) == "D:/renders/shot.0012.exr"
    assert output_for_frame("D:/renders/shot.#.exr", 3) == "D:/renders/shot.3.exr"
    assert output_for_frame("D:/renders/shot.exr", 3) == "D:/renders/shot.exr"
    native = ensure_frame_token(r"D:\renders\shot.exr")
    assert native.endswith("shot.####.exr")
    assert "#" not in output_for_frame(native, 7).split("shot.")[-1].replace("0007", "")


def test_resolve_output_relative_to_scene():
    resolved = resolve_output("beauty.exr", r"D:\shot\scene.usda")
    assert resolved.replace("\\", "/").endswith("shot/beauty.exr")


def test_kick_argv_appends_custom_flags():
    argv = build_kick_argv(
        "kick",
        "scene.usda",
        "beauty.0001.exr",
        1,
        "/World/camMain",
        split_flags('-v 2 -set options.AA_samples 4'),
    )
    assert argv[:8] == [
        "kick",
        "-i",
        "scene.usda",
        "-o",
        "beauty.0001.exr",
        "-frame",
        "1",
        "-c",
    ]
    assert argv[8] == "/World/camMain"
    assert argv[-5:] == ["-v", "2", "-set", "options.AA_samples", "4"]
    no_cam = build_kick_argv("kick", "a.usda", "b.exr", 2)
    assert "-c" not in no_cam


def test_with_log_file_appends_once():
    argv = ["kick", "-i", "a.usda"]
    logged = with_log_file(argv, r"D:\t\log.txt")
    assert logged[-2:] == ["-l", r"D:\t\log.txt"]
    assert with_log_file(logged, r"D:\other.txt") == logged
    assert log_path_from_argv(logged) == r"D:\t\log.txt"
    assert log_path_from_argv(argv) == ""


def test_show_renderview_drops_batch_window_flag():
    hidden = flags_for_renderview(split_flags("-dw -dp -nokeypress -v 2"), False)
    assert hidden == ["-dp", "-nokeypress", "-v", "2", "-dw"]
    shown = flags_for_renderview(split_flags("-dw -dp -nokeypress -v 2"), True)
    assert "-dw" not in shown
    assert "-dp" not in shown
    assert shown == ["-nokeypress", "-v", "2"]
    assert flags_for_renderview(["-v", "2"], False)[-1] == "-dw"


def test_parse_option_values():
    assert parse_option_text("int", "4") == 4
    assert parse_option_text("float", "0.015") == pytest.approx(0.015)
    assert parse_option_text("bool", "false") is False
    assert parse_option_text("bool", "yes") is True
    assert parse_option_text("float3", "1, 0, 0.5") == (1.0, 0.0, 0.5)
    assert parse_option_text("string", "spiral") == "spiral"
    with pytest.raises(ValueError):
        parse_option_text("int", "nope")
