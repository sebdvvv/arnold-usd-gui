from __future__ import annotations

import os

from pxr import Usd, UsdGeom

from arnold_usd_gui.compose import export_render_usd, render_sibling_path
from arnold_usd_gui.compose import RenderSpec
from arnold_usd_gui.scene import ArnoldOption, inspect_scene
from conftest import data_path


def test_inspect_layered_stage():
    info = inspect_scene(data_path("scene.usda"), data_path("settings.usda"))
    assert info.cameras == ["/World/camAlt", "/World/camMain"]
    assert "/Render/Preview" in info.render_settings
    assert "/Render/Final" in info.render_settings
    assert info.active_render_settings == "/Render/Preview"
    assert info.settings_cameras["/Render/Preview"] == "/World/camMain"
    assert info.settings_cameras["/Render/Final"] == "/World/camAlt"
    assert info.start == 1 and info.end == 10
    assert info.fps == 24
    assert info.up_axis == "Z"
    assert info.meters_per_unit == 0.01
    assert info.default_prim == "World"
    assert info.settings_resolution["/Render/Preview"] == (640, 360)
    assert "/Render/Final" not in info.settings_resolution
    by_key = {(item.prim_path, item.name): item for item in info.options}
    assert by_key[("/Render/Preview", "arnold:AA_samples")].value == "2"
    assert by_key[("/Render/Preview", "arnold:enable_adaptive_sampling")].value == "false"
    assert by_key[("/Render/Preview", "arnold:bucket_scanning")].value == "spiral"
    assert float(by_key[("/Render/Preview", "arnold:AA_adaptive_threshold")].value) == 0.015
    assert by_key[("/Render/options", "AA_samples")].value == "3"
    assert by_key[("/Render/options", "AA_adaptive_threshold")].variability == "uniform"


def test_export_overrides_and_save_suffix(tmp_path):
    scene = data_path("scene.usda")
    settings = data_path("settings.usda")
    info = inspect_scene(scene, settings)
    edited = []
    for option in info.options:
        if option.prim_path == "/Render/Preview" and option.name == "arnold:AA_samples":
            option.value = "7"
        if option.prim_path == "/Render/options" and option.name == "AA_adaptive_threshold":
            option.value = "0.2"
        edited.append(option)
    dest = tmp_path / "shot_render.usda"
    # Place a copy-like sibling name; sublayers stay absolute in this temp dir.
    result = export_render_usd(
        RenderSpec(
            scene_path=scene,
            dest_path=str(dest),
            settings_path=settings,
            settings_prim="/Render/Final",
            camera="/World/camAlt",
            product_name="D:/renders/shot.####.exr",
            options=edited,
            absolute_sublayers=False,
        )
    )
    text = dest.read_text(encoding="utf-8")
    assert result.settings_prim == "/Render/Final"
    assert 'renderSettingsPrimPath = "/Render/Final"' in text
    assert 'defaultPrim = "World"' in text
    assert 'upAxis = "Z"' in text
    assert "metersPerUnit = 0.01" in text
    assert "startTimeCode = 1" in text
    assert "endTimeCode = 10" in text
    assert "framesPerSecond = 24" in text
    assert text.index("settings.usda") < text.index("scene.usda")
    assert "int arnold:AA_samples = 7" in text
    assert "uniform float AA_adaptive_threshold = 0.2" in text
    assert "</World/camAlt>" in text
    assert "shot.####.exr" in text

    stage = Usd.Stage.Open(str(dest))
    assert UsdGeom.GetStageUpAxis(stage) == "Z"
    assert stage.GetStartTimeCode() == 1
    samples = stage.GetPrimAtPath("/Render/Preview").GetAttribute("arnold:AA_samples").Get()
    assert samples == 7

    sibling = render_sibling_path(scene)
    assert os.path.basename(sibling) == "scene_render.usda"
    usdc = tmp_path / "shot_render.usdc"
    export_render_usd(
        RenderSpec(
            scene_path=scene,
            dest_path=str(usdc),
            settings_path=settings,
            settings_prim="/Render/Preview",
            camera="/World/camMain",
            product_name="D:/renders/still.exr",
            options=[
                ArnoldOption(
                    prim_path="/Render/options",
                    name="GI_diffuse_depth",
                    type_name="int",
                    value="4",
                    variability="varying",
                )
            ],
            absolute_sublayers=True,
        )
    )
    crate = Usd.Stage.Open(str(usdc))
    assert crate.GetPrimAtPath("/Render/options").GetAttribute("GI_diffuse_depth").Get() == 4
    assert str(crate.GetMetadata("renderSettingsPrimPath")) == "/Render/Preview"


def test_export_writes_format_depth_and_resolution(tmp_path):
    dest = tmp_path / "fmt.usda"
    export_render_usd(
        RenderSpec(
            scene_path=data_path("scene.usda"),
            dest_path=str(dest),
            settings_path=data_path("settings.usda"),
            settings_prim="/Render/Preview",
            product_name="D:/renders/shot.png",
            image_format="png",
            bit_depth="int16",
            resolution=(1280, 720),
        )
    )
    text = dest.read_text(encoding="utf-8")
    assert "uniform int2 resolution = (1280, 720)" in text
    assert 'string arnold:driver = "driver_png"' in text
    assert 'string arnold:format = "int16"' in text
    assert "shot.png" in text


def test_subdiv_override_existing_or_all_meshes(tmp_path):
    scene = tmp_path / "meshes.usda"
    scene.write_text(
        "\n".join(
            [
                "#usda 1.0",
                "def Xform \"World\" {",
                "    def Mesh \"smooth\" {",
                "        int arnold:subdiv_iterations = 1",
                "    }",
                "    def Mesh \"hard\" {",
                "    }",
                "    def Camera \"cam\" {",
                "    }",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    existing = tmp_path / "existing.usda"
    export_render_usd(
        RenderSpec(
            scene_path=str(scene),
            dest_path=str(existing),
            subdiv_override=True,
            subdiv_catmull=True,
            subdiv_iterations=4,
            subdiv_scope="existing",
        )
    )
    text = existing.read_text(encoding="utf-8")
    assert "smooth" in text
    assert "hard" not in text
    assert "cam" not in text
    assert 'string arnold:subdiv_type = "catclark"' in text
    assert "int arnold:subdiv_iterations = 4" in text
    assert 'token subdivisionScheme = "catmullClark"' in text

    everything = tmp_path / "all.usda"
    export_render_usd(
        RenderSpec(
            scene_path=str(scene),
            dest_path=str(everything),
            subdiv_override=True,
            subdiv_catmull=False,
            subdiv_iterations=3,
            subdiv_scope="all",
        )
    )
    all_text = everything.read_text(encoding="utf-8")
    assert "smooth" in all_text
    assert "hard" in all_text
    assert "cam" not in all_text
    assert "subdiv_type" not in all_text
    assert "int arnold:subdiv_iterations = 3" in all_text


def test_bad_option_value_is_reported(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="AA_samples"):
        export_render_usd(
            RenderSpec(
                scene_path=data_path("scene.usda"),
                dest_path=str(tmp_path / "bad.usda"),
                settings_path=data_path("settings.usda"),
                options=[
                    ArnoldOption(
                        prim_path="/Render/Preview",
                        name="arnold:AA_samples",
                        type_name="int",
                        value="many",
                    )
                ],
            )
        )
