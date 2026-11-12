from arnold_usd_gui.catalog import KICK_FLAGS, OPTION_GROUPS, help_html


def test_help_lists_flags_and_parameters():
    html = help_html()
    assert "-frame" in html
    assert "-dw" in html
    assert "AA_samples" in html
    assert "renderSettingsPrimPath" in html
    assert "ARNOLD_ROOT" in html
    filtered = help_html("bucket_scanning")
    assert "bucket_scanning" in filtered
    assert "-dw" not in filtered
    names = [name for _title, rows in OPTION_GROUPS for name, _typ, _desc in rows]
    assert "AA_samples" in names
    assert "ignore_motion_blur" in names
    flags = [flag for flag, _desc in KICK_FLAGS]
    assert any(flag.startswith("-o") for flag in flags)
