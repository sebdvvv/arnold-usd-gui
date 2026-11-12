"""Parse Arnold option text back into Python values. No USD dependency."""

from __future__ import annotations

_INT_TYPES = {
    "int",
    "int64",
    "uint",
    "uint64",
    "uchar",
    "unsigned char",
}
_FLOAT_TYPES = {"float", "double", "half"}
_STRING_TYPES = {"string", "token", "asset"}
_VEC_SIZES = {
    "int2": 2,
    "int3": 3,
    "int4": 4,
    "float2": 2,
    "float3": 3,
    "float4": 4,
    "double2": 2,
    "double3": 3,
    "double4": 4,
    "color3f": 3,
    "color3d": 3,
    "color4f": 4,
    "color4d": 4,
    "normal3f": 3,
    "point3f": 3,
    "vector3f": 3,
    "vector3d": 3,
    "texCoord2f": 2,
    "texCoord3f": 3,
}


def parse_option_text(type_name: str, text: str):
    """Parse a GUI string for a USD type name such as ``int`` or ``float3``."""
    kind = (type_name or "").strip()
    raw = "" if text is None else str(text)
    if kind.endswith("[]"):
        inner = kind[:-2]
        return [parse_option_text(inner, part) for part in _split_items(raw)]
    if kind == "bool":
        return _parse_bool(raw)
    if kind in _INT_TYPES:
        token = raw.strip()
        try:
            return int(token, 10)
        except ValueError as exc:
            raise ValueError(f"Expected an integer, got '{token}'.") from exc
    if kind in _FLOAT_TYPES:
        token = raw.strip()
        try:
            return float(token)
        except ValueError as exc:
            raise ValueError(f"Expected a number, got '{token}'.") from exc
    if kind in _VEC_SIZES:
        parts = _split_items(raw)
        size = _VEC_SIZES[kind]
        if len(parts) != size:
            raise ValueError(
                f"Expected {size} values for {kind}, got {len(parts)}."
            )
        caster = int if kind.startswith("int") else float
        try:
            return tuple(caster(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"Cannot read {kind} value '{raw.strip()}'.") from exc
    if kind in _STRING_TYPES:
        return raw.strip()
    raise ValueError(f"Unsupported Arnold option type '{kind}'.")


def _parse_bool(text: str) -> bool:
    token = text.strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    raise ValueError("Expected true or false.")


def _split_items(text: str) -> list[str]:
    raw = text.strip()
    if not raw:
        return []
    if "," in raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return raw.split()
