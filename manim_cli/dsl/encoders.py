from __future__ import annotations

import math
import re
from typing import Any, List, Optional

from manim_cli.dsl.models import COLORS, DIRECTIONS, RATE_FUNCS


HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def py_str(value: str) -> str:
    return repr(value)


def py_num(value: float) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Expected finite number, got {value!r}")
    return repr(value)


def normalize_vec(value: List[float]) -> List[float]:
    if len(value) == 2:
        return [value[0], value[1], 0]
    if len(value) == 3:
        return value
    raise ValueError("Expected a 2D or 3D coordinate")


def py_vec(value: List[float]) -> str:
    vec = normalize_vec(value)
    for item in vec:
        py_num(item)
    return f"np.array({repr(vec)}, dtype=float)"


def py_color(value: str) -> str:
    if value in COLORS:
        return value
    if HEX_RE.match(value):
        return repr(value)
    raise ValueError(f"Unsupported color {value!r}")


def py_direction(value: str) -> str:
    if value not in DIRECTIONS:
        raise ValueError(f"Unsupported direction {value!r}")
    return value


def py_rate_func(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value not in RATE_FUNCS:
        raise ValueError(f"Unsupported rate function {value!r}")
    return value


def emit_point(point: List[float], coordinate_space: str, axes: Optional[str], ctx: Any) -> str:
    vec = normalize_vec(point)
    if coordinate_space == "plane":
        if not axes:
            raise ValueError("Plane coordinates require an axes id")
        axes_var = ctx.var_for(axes)
        return f"{axes_var}.c2p({py_num(vec[0])}, {py_num(vec[1])})"
    return py_vec(vec)
