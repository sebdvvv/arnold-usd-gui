"""Read cameras, RenderSettings, and Arnold options from a USD stage."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from pxr import Sdf, Usd, UsdGeom

_OPTION_TYPES = {"arnoldoptions", "arnold_options"}
_SKIP_ATTRS = {
    "purpose",
    "visibility",
    "xformOpOrder",
    "extent",
    "kind",
    "hidden",
    "active",
    "instanceable",
}


@dataclass
class ArnoldOption:
    prim_path: str
    name: str
    type_name: str
    value: str
    variability: str = "varying"


@dataclass
class SceneInfo:
    cameras: list[str] = field(default_factory=list)
    render_settings: list[str] = field(default_factory=list)
    active_render_settings: str = ""
    settings_cameras: dict[str, str] = field(default_factory=dict)
    settings_resolution: dict[str, tuple[int, int]] = field(default_factory=dict)
    options: list[ArnoldOption] = field(default_factory=list)
    start: int = 1
    end: int = 1
    fps: float | None = None
    up_axis: str = ""
    meters_per_unit: float | None = None
    default_prim: str = ""


def is_usd_path(path: str) -> bool:
    return os.path.splitext(path or "")[1].lower() in {".usd", ".usda", ".usdc"}


def inspect_scene(scene_path: str, settings_path: str = "") -> SceneInfo:
    """Read the scene, optionally with a RenderSettings USD layered above it."""
    scene_path = os.path.abspath(scene_path)
    settings_path = os.path.abspath(settings_path) if settings_path else ""
    if not os.path.isfile(scene_path):
        raise ValueError(f"USD file not found:\n{scene_path}")
    if settings_path and not os.path.isfile(settings_path):
        raise ValueError(f"RenderSettings USD not found:\n{settings_path}")

    scene_meta = _file_metadata(scene_path)
    settings_meta = _file_metadata(settings_path) if settings_path else {}
    stage = _open_stage(scene_path, settings_path)

    cameras: list[str] = []
    settings: list[str] = []
    settings_cameras: dict[str, str] = {}
    settings_resolution: dict[str, tuple[int, int]] = {}
    options: list[ArnoldOption] = []

    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if _is_camera(prim):
            cameras.append(path)
        is_settings = _is_render_settings(prim)
        is_options = prim.GetTypeName().lower() in _OPTION_TYPES
        if is_settings:
            settings.append(path)
            settings_cameras[path] = _camera_target(prim)
            resolution = _resolution(prim)
            if resolution is not None:
                settings_resolution[path] = resolution
        if is_settings or is_options:
            options.extend(_options_on_prim(prim, settings=is_settings))

    cameras.sort()
    settings.sort()
    options.sort(key=lambda item: (item.prim_path, item.name))

    meta_prim = str(settings_meta.get("render_settings") or scene_meta.get("render_settings") or "")
    active = ""
    if meta_prim and (meta_prim in settings or stage.GetPrimAtPath(meta_prim)):
        active = meta_prim
        if meta_prim not in settings:
            settings.append(meta_prim)
            settings.sort()
    elif len(settings) == 1:
        active = settings[0]

    start = _first(scene_meta.get("start"), settings_meta.get("start"), 1.0)
    end = _first(scene_meta.get("end"), settings_meta.get("end"), start)
    fps = _first(scene_meta.get("fps"), settings_meta.get("fps"))
    return SceneInfo(
        cameras=cameras,
        render_settings=settings,
        active_render_settings=active,
        settings_cameras=settings_cameras,
        settings_resolution=settings_resolution,
        options=options,
        start=_as_frame(start),
        end=_as_frame(end),
        fps=None if fps is None else float(fps),
        up_axis=str(_first(scene_meta.get("up"), settings_meta.get("up"), "") or ""),
        meters_per_unit=_first(scene_meta.get("meters"), settings_meta.get("meters")),
        default_prim=str(_first(scene_meta.get("default"), settings_meta.get("default"), "") or ""),
    )


def _open_stage(scene_path: str, settings_path: str) -> Usd.Stage:
    if not settings_path:
        stage = Usd.Stage.Open(scene_path)
        if stage is None:
            raise ValueError(f"Could not open USD:\n{scene_path}")
        return stage
    layer = Sdf.Layer.CreateAnonymous("arnold_usd_gui_inspect.usda")
    layer.subLayerPaths = [_forward(settings_path), _forward(scene_path)]
    stage = Usd.Stage.Open(layer)
    if stage is None:
        raise ValueError("Could not compose the scene with the RenderSettings USD.")
    return stage


def _file_metadata(path: str) -> dict:
    stage = Usd.Stage.Open(path)
    if stage is None:
        raise ValueError(f"Could not open USD:\n{path}")
    layer = stage.GetRootLayer()
    pseudo = layer.pseudoRoot
    up = ""
    if pseudo.HasInfo("upAxis"):
        up = str(pseudo.GetInfo("upAxis") or "")
    meters = None
    if UsdGeom.StageHasAuthoredMetersPerUnit(stage):
        meters = float(UsdGeom.GetStageMetersPerUnit(stage))
    render_settings = ""
    try:
        raw = stage.GetMetadata("renderSettingsPrimPath")
        if raw:
            render_settings = str(raw)
    except Exception:  # noqa: BLE001
        render_settings = ""
    return {
        "start": layer.startTimeCode if layer.HasStartTimeCode() else None,
        "end": layer.endTimeCode if layer.HasEndTimeCode() else None,
        "fps": layer.framesPerSecond if layer.HasFramesPerSecond() else None,
        "tps": layer.timeCodesPerSecond if layer.HasTimeCodesPerSecond() else None,
        "up": up,
        "meters": meters,
        "default": str(layer.defaultPrim) if layer.HasDefaultPrim() else "",
        "render_settings": render_settings,
    }


def _options_on_prim(prim, settings: bool) -> list[ArnoldOption]:
    found: list[ArnoldOption] = []
    for attr in prim.GetAttributes():
        name = attr.GetName()
        if settings and not name.startswith("arnold:"):
            continue
        if not settings and _skip_attr(name):
            continue
        if not attr.HasAuthoredValue():
            continue
        try:
            value = attr.Get()
        except Exception:  # noqa: BLE001
            continue
        if value is None:
            continue
        variability = "varying"
        try:
            if attr.GetVariability() == Sdf.VariabilityUniform:
                variability = "uniform"
        except Exception:  # noqa: BLE001
            pass
        found.append(
            ArnoldOption(
                prim_path=str(prim.GetPath()),
                name=name,
                type_name=_type_token(attr.GetTypeName()),
                value=format_usd_value(value),
                variability=variability,
            )
        )
    return found


def _is_camera(prim) -> bool:
    try:
        if prim.IsA(UsdGeom.Camera):
            return True
    except Exception:  # noqa: BLE001
        pass
    return prim.GetTypeName() == "Camera"


def _is_render_settings(prim) -> bool:
    """Type name only. Some USD builds ship pxr.UsdRender without schema classes."""
    if prim.GetTypeName() == "RenderSettings":
        return True
    try:
        return any("RenderSettings" in schema for schema in prim.GetAppliedSchemas())
    except Exception:  # noqa: BLE001
        return False


def _resolution(prim) -> tuple[int, int] | None:
    attr = prim.GetAttribute("resolution")
    if not attr or not attr.HasAuthoredValue():
        return None
    try:
        value = attr.Get()
    except Exception:  # noqa: BLE001
        return None
    if value is None or len(value) < 2:
        return None
    width, height = int(value[0]), int(value[1])
    if width <= 0 or height <= 0:
        return None
    return width, height


def _camera_target(prim) -> str:
    rel = prim.GetRelationship("camera")
    if not rel:
        return ""
    try:
        targets = rel.GetTargets()
    except Exception:  # noqa: BLE001
        return ""
    if not targets:
        return ""
    return str(targets[0])


def _skip_attr(name: str) -> bool:
    if name.startswith("xformOp:"):
        return True
    return name in _SKIP_ATTRS


def _type_token(type_name) -> str:
    text = str(type_name).strip()
    if "ValueTypeName" in text and "(" in text:
        text = text.split("(", 1)[-1].rstrip(")")
    return text.strip().strip("'\"")


def format_usd_value(value) -> str:
    """Compact text for the options table."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Sdf.AssetPath):
        return value.path
    type_name = type(value).__name__
    if type_name.startswith("Vec") or type_name.startswith("Quat"):
        return ", ".join(_num(value[index]) for index in range(len(value)))
    if isinstance(value, float):
        return _num(value)
    if not isinstance(value, (str, bytes)) and hasattr(value, "__iter__"):
        return ", ".join(format_usd_value(item) for item in value)
    return str(value)


def _num(value) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _as_frame(value) -> int:
    return int(round(float(value)))


def _first(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        return value
    return None


def _forward(path: str) -> str:
    return os.path.abspath(path).replace("\\", "/")
