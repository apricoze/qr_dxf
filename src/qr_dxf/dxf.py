"""DXF export helpers for QR modules."""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from .matrix_utils import finder_pattern_modules


def qr_matrix_to_dxf(
    matrix: Sequence[Sequence[bool]],
    module_size: float = 1.0,
    corner_radius: float = 0.0,
    *,
    body_corner_radius: float | None = None,
    eye_frame_corner_radius: float | None = None,
    eye_ball_corner_radius: float | None = None,
    layer: str = "QR",
) -> str:
    if module_size <= 0:
        raise ValueError("module_size must be positive")
    size = len(matrix)
    if size == 0:
        raise ValueError("matrix must not be empty")

    default_radius = _clamp_radius(module_size, corner_radius)
    body_radius = _clamp_radius(
        module_size, corner_radius if body_corner_radius is None else body_corner_radius
    )
    eye_frame_radius = _clamp_radius(
        module_size,
        body_radius if eye_frame_corner_radius is None else eye_frame_corner_radius,
    )
    eye_ball_radius = _clamp_radius(
        module_size,
        body_radius if eye_ball_corner_radius is None else eye_ball_corner_radius,
    )

    eye_frame_modules, eye_ball_modules = finder_pattern_modules(matrix)
    entities: List[str] = []
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            if not value:
                continue
            if (x, y) in eye_ball_modules:
                radius = eye_ball_radius
            elif (x, y) in eye_frame_modules:
                radius = eye_frame_radius
            else:
                radius = body_radius if body_corner_radius is not None else default_radius
            left_on = x > 0 and matrix[y][x - 1]
            right_on = x + 1 < size and matrix[y][x + 1]
            top_on = y > 0 and matrix[y - 1][x]
            bottom_on = y + 1 < size and matrix[y + 1][x]
            entities.extend(
                _module_polyline(
                    x,
                    y,
                    size,
                    module_size,
                    radius,
                    layer,
                    left_on,
                    right_on,
                    top_on,
                    bottom_on,
                )
            )
    header = _dxf_header(layer)
    footer = _dxf_footer()
    return "\n".join(header + entities + footer) + "\n"


def _clamp_radius(module_size: float, radius: float) -> float:
    return max(0.0, min(radius, module_size / 2.0))


def _module_polyline(
    x: int,
    y: int,
    size: int,
    module: float,
    radius: float,
    layer: str,
    left_on: bool,
    right_on: bool,
    top_on: bool,
    bottom_on: bool,
) -> List[str]:
    x0 = x * module
    y0 = (size - y - 1) * module
    x1 = x0 + module
    y1 = y0 + module
    if radius <= 1e-9:
        points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        bulges = [0.0, 0.0, 0.0, 0.0]
    else:
        k = math.tan(math.pi / 8.0)

        top_exposed = not top_on
        right_exposed = not right_on
        bottom_exposed = not bottom_on
        left_exposed = not left_on

        tl_radius = radius if top_exposed and left_exposed else 0.0
        tr_radius = radius if top_exposed and right_exposed else 0.0
        br_radius = radius if bottom_exposed and right_exposed else 0.0
        bl_radius = radius if bottom_exposed and left_exposed else 0.0

        points: List[Tuple[float, float]] = []
        bulges: List[float] = []

        def _add_point(point: tuple[float, float], bulge: float) -> None:
            if points and math.isclose(point[0], points[-1][0]) and math.isclose(point[1], points[-1][1]):
                bulges[-1] = bulge
            else:
                points.append(point)
                bulges.append(bulge)

        # Top edge (left to right)
        _add_point((x0 + tl_radius, y1), 0.0)
        top_edge_end = x1 - tr_radius
        _add_point((top_edge_end, y1), k if tr_radius > 0.0 else 0.0)
        if tr_radius > 0.0:
            _add_point((x1, y1 - tr_radius), 0.0)

        # Right edge (top to bottom)
        right_edge_end = y0 + br_radius
        _add_point((x1, right_edge_end), k if br_radius > 0.0 else 0.0)
        if br_radius > 0.0:
            _add_point((x1 - br_radius, y0), 0.0)

        # Bottom edge (right to left)
        bottom_edge_end = x0 + bl_radius
        _add_point((bottom_edge_end, y0), k if bl_radius > 0.0 else 0.0)
        if bl_radius > 0.0:
            _add_point((x0, y0 + bl_radius), 0.0)

        # Left edge (bottom to top)
        left_edge_end = y1 - tl_radius
        _add_point((x0, left_edge_end), k if tl_radius > 0.0 else 0.0)
    return _lwpolyline(points, bulges, layer)


def _lwpolyline(points: Sequence[Tuple[float, float]], bulges: Sequence[float], layer: str) -> List[str]:
    values = [
        "0", "LWPOLYLINE",
        "8", layer,
        "90", str(len(points)),
        "70", "1",
    ]
    for (x, y), bulge in zip(points, bulges):
        values.extend(["10", f"{x:.6f}", "20", f"{y:.6f}"])
        if abs(bulge) > 1e-9:
            values.extend(["42", f"{bulge:.6f}"])
    return values


def _dxf_header(layer: str) -> List[str]:
    return [
        "0", "SECTION", "2", "HEADER", "0", "ENDSEC",
        "0", "SECTION", "2", "TABLES",
        "0", "TABLE", "2", "LAYER", "70", "1",
        "0", "LAYER", "2", layer, "70", "0", "62", "7", "6", "CONTINUOUS",
        "0", "ENDTAB", "0", "ENDSEC",
        "0", "SECTION", "2", "ENTITIES",
    ]


def _dxf_footer() -> List[str]:
    return ["0", "ENDSEC", "0", "EOF"]
