"""Build the temporary USD submitted to kick.

Layer strength, strongest first:

1. Opinions authored here (camera, output, Arnold option edits, renderSettingsPrimPath).
2. Optional RenderSettings USD.
3. The scene USD.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from dataclasses import dataclass, field

from pxr import Gf, Sdf, Usd, UsdGeom

from arnold_usd_gui.scene import ArnoldOption, _file_metadata, inspect_scene
from arnold_usd_gui.values import parse_option_text

_USD_EXTENSIONS = {".usd", ".usda", ".usdc"}


@dataclass(frozen=True)
class ImageFormat:
    label: str
    key: str
    driver: str
    extension: str
    depths: tuple[tuple[str, str], ...]


# Arnold reads ``arnold:driver`` on the RenderProduct and the matching
# driver parameter (``half_precision`` for EXR, ``format`` for PNG and TIFF).
IMAGE_FORMATS: tuple[ImageFormat, ...] = (
    ImageFormat(
        "OpenEXR",
        "exr",
        "driver_exr",
        ".exr",
        (("16-bit half", "half"), ("32-bit float", "float")),
    ),
    ImageFormat(
        "PNG",
        "png",
        "driver_png",
        ".png",
        (("8-bit", "int8"), ("16-bit", "int16")),
    ),
    ImageFormat(
        "TIFF",
        "tif",
        "driver_tiff",
        ".tif",
        (("8-bit", "uint8"), ("16-bit", "uint16"), ("32-bit float", "float")),
    ),
    ImageFormat(
        "JPEG",
        "jpg",
        "driver_jpeg",
        ".jpg",
        (("8-bit", "uint8"),),
    ),
)


def image_format(key: str) -> ImageFormat:
    wanted = (key or "").strip().lower()
    for item in IMAGE_FORMATS:
        if item.key == wanted:
            return item
    return IMAGE_FORMATS[0]


@dataclass
class RenderSpec:
    scene_path: str
    dest_path: str
    settings_path: str = ""
    settings_prim: str = ""
    camera: str = ""
    product_name: str = ""
    image_format: str = "exr"
    bit_depth: str = "half"
    resolution: tuple[int, int] | None = None
    subdiv_override: bool = False
    subdiv_catmull: bool = True
    subdiv_iterations: int = 2
    subdiv_scope: str = "existing"
    options: list[ArnoldOption] = field(default_factory=list)
    absolute_sublayers: bool = True


@dataclass
class ExportResult:
    path: str
    settings_prim: str
    layers: list[str]


def render_sibling_path(scene_path: str) -> str:
    """``shot.usda`` → ``shot_render.usda`` beside the source, same extension."""
    folder, name = os.path.split(os.path.abspath(scene_path))
    stem, ext = os.path.splitext(name)
    if ext.lower() not in _USD_EXTENSIONS:
        ext = ".usda"
    return os.path.join(folder, stem + "_render" + ext)


def temporary_usd_path(scene_path: str) -> str:
    folder = os.path.join(tempfile.gettempdir(), "arnold-usd-gui")
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(scene_path))[0]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[:48] or "scene"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(folder, f"{stem}_{stamp}.usda")
    if os.path.exists(path):
        path = os.path.join(folder, f"{stem}_{stamp}_{os.getpid()}.usda")
    return path


def cleanup_temporary_usd(keep: str = "") -> None:
    folder = os.path.join(tempfile.gettempdir(), "arnold-usd-gui")
    if not os.path.isdir(folder):
        return
    keep_abs = os.path.normcase(os.path.abspath(keep)) if keep else ""
    for name in os.listdir(folder):
        if not name.lower().endswith(".usda"):
            continue
        path = os.path.join(folder, name)
        if keep_abs and os.path.normcase(os.path.abspath(path)) == keep_abs:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


def export_render_usd(spec: RenderSpec) -> ExportResult:
    """Write ``spec.dest_path`` and return which RenderSettings prim was targeted."""
    scene_path = os.path.abspath(spec.scene_path)
    if not os.path.isfile(scene_path):
        raise ValueError(f"USD file not found:\n{scene_path}")
    settings_path = os.path.abspath(spec.settings_path) if spec.settings_path else ""
    if settings_path and not os.path.isfile(settings_path):
        raise ValueError(f"RenderSettings USD not found:\n{settings_path}")

    info = inspect_scene(scene_path, settings_path)
    scene_meta = _file_metadata(scene_path)
    settings_meta = _file_metadata(settings_path) if settings_path else {}

    dest = os.path.abspath(spec.dest_path)
    folder = os.path.dirname(dest)
    if folder:
        os.makedirs(folder, exist_ok=True)

    layers: list[str] = []
    if settings_path:
        layers.append(_reference(settings_path, dest, spec.absolute_sublayers))
    layers.append(_reference(scene_path, dest, spec.absolute_sublayers))

    layer = Sdf.Layer.CreateAnonymous("arnold_usd_gui_render.usda")
    layer.comment = "Authored by arnold-usd-gui for Arnold kick."
    layer.subLayerPaths = layers
    _copy_time(layer, scene_meta, settings_meta)

    stage = Usd.Stage.Open(layer)
    if stage is None:
        raise ValueError("Could not build the render USD.")

    if info.up_axis:
        UsdGeom.SetStageUpAxis(stage, info.up_axis)
    if info.meters_per_unit is not None:
        UsdGeom.SetStageMetersPerUnit(stage, float(info.meters_per_unit))

    settings_prim = _resolve_settings_prim(stage, spec.settings_prim, info)
    prim = _over_or_define(stage, settings_prim, "RenderSettings")

    stage.SetMetadata("renderSettingsPrimPath", settings_prim)

    if spec.camera:
        _set_targets(prim, "camera", [spec.camera])

    if spec.resolution and spec.resolution[0] > 0 and spec.resolution[1] > 0:
        _set_resolution(prim, spec.resolution[0], spec.resolution[1])

    if spec.product_name:
        _author_product(
            stage,
            prim,
            spec.product_name.replace("\\", "/"),
            spec.image_format,
            spec.bit_depth,
        )

    for option in spec.options:
        _author_option(stage, option)

    if spec.subdiv_override:
        _author_subdiv(stage, spec)

    if info.default_prim:
        default_path = "/" + info.default_prim.strip("/")
        default_prim = stage.GetPrimAtPath(default_path)
        if not default_prim or not default_prim.IsValid():
            default_prim = stage.OverridePrim(default_path)
        stage.SetDefaultPrim(default_prim)

    if not layer.Export(dest):
        raise ValueError(f"Could not write USD:\n{dest}")
    return ExportResult(path=dest, settings_prim=settings_prim, layers=list(layers))


def _copy_time(layer: Sdf.Layer, scene_meta: dict, settings_meta: dict) -> None:
    start = _meta_first(scene_meta, settings_meta, "start")
    end = _meta_first(scene_meta, settings_meta, "end")
    fps = _meta_first(scene_meta, settings_meta, "fps")
    tps = _meta_first(scene_meta, settings_meta, "tps")
    if start is not None:
        layer.startTimeCode = float(start)
    if end is not None:
        layer.endTimeCode = float(end)
    if fps is not None:
        layer.framesPerSecond = float(fps)
    if tps is not None:
        layer.timeCodesPerSecond = float(tps)


def _meta_first(scene_meta: dict, settings_meta: dict, key: str):
    if scene_meta.get(key) is not None:
        return scene_meta[key]
    if settings_meta.get(key) is not None:
        return settings_meta[key]
    return None


def _resolve_settings_prim(stage: Usd.Stage, requested: str, info) -> str:
    requested = (requested or "").strip()
    if requested:
        return requested
    if info.active_render_settings:
        return info.active_render_settings
    if info.render_settings:
        return info.render_settings[0]
    for prim in stage.Traverse():
        if prim.GetTypeName() == "RenderSettings":
            return str(prim.GetPath())
    return "/Render/arnold_usd_gui"


def _author_product(
    stage: Usd.Stage,
    settings_prim,
    product_name: str,
    image_format_key: str,
    bit_depth: str,
) -> None:
    targets = []
    rel = settings_prim.GetRelationship("products")
    if rel:
        try:
            targets = list(rel.GetTargets())
        except Exception:  # noqa: BLE001
            targets = []
    if targets:
        product = stage.OverridePrim(targets[0])
    else:
        product_path = "/Render/Products/arnold_usd_gui"
        product = _over_or_define(stage, product_path, "RenderProduct")
        _set_token(product, "productType", "raster")
        _set_targets(settings_prim, "products", [product_path])
    _set_token(product, "productName", product_name)
    fmt = image_format(image_format_key)
    _set_string(product, "arnold:driver", fmt.driver)
    _author_bit_depth(product, fmt, bit_depth)


def _author_bit_depth(product, fmt: ImageFormat, bit_depth: str) -> None:
    allowed = {key for _label, key in fmt.depths}
    chosen = bit_depth if bit_depth in allowed else fmt.depths[0][1]
    if fmt.key == "exr":
        _set_bool(product, "arnold:half_precision", chosen == "half")
        return
    if fmt.key == "jpg":
        return
    _set_string(product, "arnold:format", chosen)


def _set_resolution(prim, width: int, height: int) -> None:
    attr = prim.CreateAttribute(
        "resolution",
        Sdf.ValueTypeNames.Int2,
        custom=False,
        variability=Sdf.VariabilityUniform,
    )
    attr.Set(Gf.Vec2i(int(width), int(height)))


def _over_or_define(stage: Usd.Stage, path: str, type_name: str):
    existing = stage.GetPrimAtPath(path)
    if existing and existing.IsValid():
        return stage.OverridePrim(path)
    return stage.DefinePrim(path, type_name)


def _set_targets(prim, name: str, targets: list[str]) -> None:
    rel = prim.CreateRelationship(name)
    rel.SetTargets([Sdf.Path(target) for target in targets])


def _set_token(prim, name: str, value: str) -> None:
    attr = prim.CreateAttribute(name, Sdf.ValueTypeNames.Token, custom=True)
    attr.Set(value)


def _set_string(prim, name: str, value: str) -> None:
    attr = prim.CreateAttribute(name, Sdf.ValueTypeNames.String, custom=True)
    attr.Set(value)


def _set_bool(prim, name: str, value: bool) -> None:
    attr = prim.CreateAttribute(name, Sdf.ValueTypeNames.Bool, custom=True)
    attr.Set(bool(value))


def _set_int(prim, name: str, value: int) -> None:
    attr = prim.CreateAttribute(name, Sdf.ValueTypeNames.Int, custom=True)
    attr.Set(int(value))


_SUBDIV_ATTRS = ("arnold:subdiv_type", "arnold:subdiv_iterations", "subdivisionScheme")


def _author_subdiv(stage: Usd.Stage, spec: RenderSpec) -> None:
    """Force Arnold subdivision onto meshes in this layer."""
    iterations = max(0, int(spec.subdiv_iterations))
    scope = spec.subdiv_scope if spec.subdiv_scope in {"existing", "all"} else "existing"
    for prim in stage.Traverse():
        if scope == "all":
            if not _is_mesh(prim):
                continue
        elif not _has_subdiv_attr(prim):
            continue
        over = stage.OverridePrim(prim.GetPath())
        if spec.subdiv_catmull:
            _set_string(over, "arnold:subdiv_type", "catclark")
            scheme = over.CreateAttribute(
                "subdivisionScheme",
                Sdf.ValueTypeNames.Token,
                custom=False,
            )
            scheme.Set("catmullClark")
        _set_int(over, "arnold:subdiv_iterations", iterations)


def _has_subdiv_attr(prim) -> bool:
    for name in _SUBDIV_ATTRS:
        attr = prim.GetAttribute(name)
        if attr and attr.HasAuthoredValue():
            return True
    return False


def _is_mesh(prim) -> bool:
    if prim.GetTypeName() in {"Mesh", "Polymesh"}:
        return True
    try:
        return bool(prim.IsA(UsdGeom.Mesh))
    except Exception:  # noqa: BLE001
        return False


def _author_option(stage: Usd.Stage, option: ArnoldOption) -> None:
    if not option.prim_path or not option.name:
        return
    try:
        parsed = parse_option_text(option.type_name, option.value)
    except ValueError as exc:
        raise ValueError(
            f"{option.name} on {option.prim_path}: {exc}"
        ) from exc
    prim = stage.GetPrimAtPath(option.prim_path)
    if not prim or not prim.IsValid():
        prim = stage.OverridePrim(option.prim_path)
    else:
        prim = stage.OverridePrim(option.prim_path)
    variability = (
        Sdf.VariabilityUniform if option.variability == "uniform" else Sdf.VariabilityVarying
    )
    attr = prim.CreateAttribute(option.name, _sdf_type(option.type_name), custom=True, variability=variability)
    attr.Set(_to_usd(option.type_name, parsed))


def _sdf_type(type_name: str):
    kind = (type_name or "").strip()
    table = {
        "bool": Sdf.ValueTypeNames.Bool,
        "int": Sdf.ValueTypeNames.Int,
        "int64": Sdf.ValueTypeNames.Int64,
        "uint": Sdf.ValueTypeNames.UInt,
        "uint64": Sdf.ValueTypeNames.UInt64,
        "float": Sdf.ValueTypeNames.Float,
        "double": Sdf.ValueTypeNames.Double,
        "half": Sdf.ValueTypeNames.Half,
        "string": Sdf.ValueTypeNames.String,
        "token": Sdf.ValueTypeNames.Token,
        "asset": Sdf.ValueTypeNames.Asset,
        "int2": Sdf.ValueTypeNames.Int2,
        "int3": Sdf.ValueTypeNames.Int3,
        "int4": Sdf.ValueTypeNames.Int4,
        "float2": Sdf.ValueTypeNames.Float2,
        "float3": Sdf.ValueTypeNames.Float3,
        "float4": Sdf.ValueTypeNames.Float4,
        "double2": Sdf.ValueTypeNames.Double2,
        "double3": Sdf.ValueTypeNames.Double3,
        "double4": Sdf.ValueTypeNames.Double4,
        "color3f": Sdf.ValueTypeNames.Color3f,
        "color3d": Sdf.ValueTypeNames.Color3d,
        "color4f": Sdf.ValueTypeNames.Color4f,
        "normal3f": Sdf.ValueTypeNames.Normal3f,
        "point3f": Sdf.ValueTypeNames.Point3f,
        "vector3f": Sdf.ValueTypeNames.Vector3f,
        "texCoord2f": Sdf.ValueTypeNames.TexCoord2f,
        "int[]": Sdf.ValueTypeNames.IntArray,
        "float[]": Sdf.ValueTypeNames.FloatArray,
        "string[]": Sdf.ValueTypeNames.StringArray,
        "token[]": Sdf.ValueTypeNames.TokenArray,
    }
    if kind not in table:
        raise ValueError(f"Unsupported Arnold option type '{kind}'.")
    return table[kind]


def _to_usd(type_name: str, parsed):
    kind = (type_name or "").strip()
    if kind == "int2":
        return Gf.Vec2i(*parsed)
    if kind == "int3":
        return Gf.Vec3i(*parsed)
    if kind == "int4":
        return Gf.Vec4i(*parsed)
    if kind in {"float2", "texCoord2f"}:
        return Gf.Vec2f(*parsed)
    if kind == "double2":
        return Gf.Vec2d(*parsed)
    if kind in {"float3", "color3f", "normal3f", "point3f", "vector3f"}:
        return Gf.Vec3f(*parsed)
    if kind in {"double3", "color3d"}:
        return Gf.Vec3d(*parsed)
    if kind in {"float4", "color4f"}:
        return Gf.Vec4f(*parsed)
    if kind == "double4":
        return Gf.Vec4d(*parsed)
    if kind == "asset":
        return Sdf.AssetPath(parsed)
    return parsed


def _reference(target: str, dest: str, absolute: bool) -> str:
    target_abs = os.path.abspath(target)
    if absolute:
        return target_abs.replace("\\", "/")
    dest_dir = os.path.dirname(os.path.abspath(dest))
    try:
        rel = os.path.relpath(target_abs, dest_dir)
    except ValueError:
        rel = target_abs
    return rel.replace("\\", "/")
