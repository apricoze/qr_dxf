"""DXF export helpers for QR modules."""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Set, Tuple

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

    eye_frame_modules, eye_ball_modules = finder_pattern_modules(matrix)
    eye_ball_groups = _group_adjacent_modules(eye_ball_modules)
    eye_ball_bboxes = [_bounding_box(group) for group in eye_ball_groups]
    eye_ball_bbox_map: Dict[Tuple[int, int], Tuple[int, int, int, int]] = {}
    for bbox, group in zip(eye_ball_bboxes, eye_ball_groups):
        for coord in group:
            eye_ball_bbox_map[coord] = bbox

    if eye_ball_bboxes:
        span_x = eye_ball_bboxes[0][2] - eye_ball_bboxes[0][0] + 1
        span_y = eye_ball_bboxes[0][3] - eye_ball_bboxes[0][1] + 1
        eye_ball_span = min(span_x, span_y)
    else:
        eye_ball_span = 1

    eye_frame_radius = _clamp_radius(
        module_size,
        body_radius if eye_frame_corner_radius is None else eye_frame_corner_radius,
    )
    eye_ball_radius = _clamp_radius(
        module_size * eye_ball_span,
        body_radius if eye_ball_corner_radius is None else eye_ball_corner_radius,
    )

    entities: List[str] = []
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            if not value:
                continue
            if (x, y) in eye_ball_modules:
                bbox = eye_ball_bbox_map.get((x, y))
                if bbox is None:
                    continue
                origin = (bbox[0], bbox[1])
                if (x, y) != origin:
                    continue
                x_min, y_min, x_max, y_max = bbox
                entities.extend(
                    _rounded_rect_polyline(
                        x_min * module_size,
                        (size - y_max - 1) * module_size,
                        (x_max + 1) * module_size,
                        (size - y_min) * module_size,
                        eye_ball_radius,
                        layer,
                    )
                )
                continue
            if (x, y) in eye_frame_modules:
                radius = eye_frame_radius
            else:
                radius = body_radius if body_corner_radius is not None else default_radius
            entities.extend(
                _module_polyline(x, y, size, module_size, radius, layer)
            )
    header = _dxf_header(layer)
    footer = _dxf_footer()
    return "\n".join(header + entities + footer) + "\n"


def _clamp_radius(module_size: float, radius: float) -> float:
    return max(0.0, min(radius, module_size / 2.0))


def _module_polyline(x: int, y: int, size: int, module: float, radius: float, layer: str) -> List[str]:
    x0 = x * module
    y0 = (size - y - 1) * module
    x1 = x0 + module
    y1 = y0 + module
    return _rounded_rect_polyline(x0, y0, x1, y1, radius, layer)


def _rounded_rect_polyline(
    x0: float, y0: float, x1: float, y1: float, radius: float, layer: str
) -> List[str]:
    if radius <= 1e-9:
        points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        bulges = [0.0, 0.0, 0.0, 0.0]
    else:
        width = max(0.0, x1 - x0)
        height = max(0.0, y1 - y0)
        r = min(radius, width / 2.0, height / 2.0)
        k = math.tan(math.pi / 8.0)
        points = [
            (x0 + r, y1), (x1 - r, y1), (x1, y1 - r), (x1, y0 + r),
            (x1 - r, y0), (x0 + r, y0), (x0, y0 + r), (x0, y1 - r),
        ]
        bulges = [0.0, k, 0.0, k, 0.0, k, 0.0, k]
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


def _group_adjacent_modules(
    modules: Set[Tuple[int, int]]
) -> List[Set[Tuple[int, int]]]:
    remaining = set(modules)
    groups: List[Set[Tuple[int, int]]] = []
    while remaining:
        start = remaining.pop()
        group = {start}
        stack = [start]
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) in remaining:
                    remaining.remove((nx, ny))
                    group.add((nx, ny))
                    stack.append((nx, ny))
        groups.append(group)
    return groups


def _bounding_box(coords: Set[Tuple[int, int]]) -> Tuple[int, int, int, int]:
    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    return min(xs), min(ys), max(xs), max(ys)
