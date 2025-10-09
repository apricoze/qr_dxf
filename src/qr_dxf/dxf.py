"""DXF export helpers for QR modules."""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Set, Tuple

from .matrix_utils import Coordinate, finder_pattern_modules


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

    active_modules: Set[Coordinate] = {
        (x, y)
        for y, row in enumerate(matrix)
        for x, value in enumerate(row)
        if value
    }

    body_radius = body_radius if body_corner_radius is not None else default_radius

    body_modules = active_modules - eye_ball_modules - eye_frame_modules

    for module_set, radius in (
        (eye_ball_modules, eye_ball_radius),
        (eye_frame_modules, eye_frame_radius),
        (body_modules, body_radius),
    ):
        if not module_set:
            continue
        components = _connected_components(module_set)
        for component in components:
            entities.extend(
                _component_entities(component, size, module_size, radius, layer)
            )
    header = _dxf_header(layer)
    footer = _dxf_footer()
    return "\n".join(header + entities + footer) + "\n"


def _clamp_radius(module_size: float, radius: float) -> float:
    return max(0.0, min(radius, module_size / 2.0))


def _connected_components(modules: Set[Coordinate]) -> List[Set[Coordinate]]:
    remaining = set(modules)
    components: List[Set[Coordinate]] = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        component = {start}
        while stack:
            cx, cy = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = (cx + dx, cy + dy)
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components


def _component_entities(
    component: Set[Coordinate],
    size: int,
    module_size: float,
    radius: float,
    layer: str,
) -> List[str]:
    entities: List[str] = []
    loops = _component_loops(component, size)
    for loop in loops:
        points, bulges = _rounded_loop(loop, module_size, radius)
        if len(points) < 2:
            continue
        entities.extend(_lwpolyline(points, bulges, layer))
    return entities


def _component_loops(component: Set[Coordinate], size: int) -> List[List[Tuple[int, int]]]:
    edges: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for x, y in component:
        x0 = x
        x1 = x + 1
        y0 = size - y - 1
        y1 = y0 + 1
        if (x, y + 1) not in component:
            edges.setdefault((x0, y0), []).append((x1, y0))
        if (x, y - 1) not in component:
            edges.setdefault((x1, y1), []).append((x0, y1))
        if (x + 1, y) not in component:
            edges.setdefault((x1, y0), []).append((x1, y1))
        if (x - 1, y) not in component:
            edges.setdefault((x0, y1), []).append((x0, y0))

    loops: List[List[Tuple[int, int]]] = []
    while edges:
        start = next(iter(edges))
        loop: List[Tuple[int, int]] = []
        current = start
        while True:
            loop.append(current)
            targets = edges[current]
            next_point = targets.pop()
            if not targets:
                del edges[current]
            current = next_point
            if current == start:
                break
        loops.append(loop)
    return loops


def _rounded_loop(
    loop: Sequence[Tuple[int, int]], module_size: float, radius: float
) -> Tuple[List[Tuple[float, float]], List[float]]:
    if not loop:
        return [], []
    scaled = [(x * module_size, y * module_size) for x, y in loop]
    if len(scaled) < 2:
        return [], []

    area = _polygon_area(scaled)
    if abs(area) <= 1e-12:
        bulges = [0.0] * len(scaled)
        return scaled, bulges

    orientation_sign = 1.0 if area > 0.0 else -1.0
    result_points: List[Tuple[float, float]] = []
    result_bulges: List[float] = []
    n = len(scaled)
    k = math.tan(math.pi / 8.0)

    for i in range(n):
        prev_point = scaled[(i - 1) % n]
        curr_point = scaled[i]
        next_point = scaled[(i + 1) % n]
        dx1 = curr_point[0] - prev_point[0]
        dy1 = curr_point[1] - prev_point[1]
        dx2 = next_point[0] - curr_point[0]
        dy2 = next_point[1] - curr_point[1]
        len1 = math.hypot(dx1, dy1)
        len2 = math.hypot(dx2, dy2)
        if len1 <= 1e-9 or len2 <= 1e-9:
            r = 0.0
            cross = 0.0
        else:
            cross = dx1 * dy2 - dy1 * dx2
            is_convex = orientation_sign * cross > 1e-9
            if is_convex and radius > 1e-9:
                r = min(radius, len1 / 2.0, len2 / 2.0)
            else:
                r = 0.0

        if r <= 1e-9:
            if result_points and _points_close(result_points[-1], curr_point):
                result_bulges[-1] = 0.0
            else:
                result_points.append(curr_point)
                result_bulges.append(0.0)
            continue

        ux1 = dx1 / len1
        uy1 = dy1 / len1
        ux2 = dx2 / len2
        uy2 = dy2 / len2
        start_point = (curr_point[0] - ux1 * r, curr_point[1] - uy1 * r)
        end_point = (curr_point[0] + ux2 * r, curr_point[1] + uy2 * r)

        bulge = math.copysign(k, cross)

        if result_points and _points_close(result_points[-1], start_point):
            result_bulges[-1] = bulge
        else:
            result_points.append(start_point)
            result_bulges.append(bulge)

        if result_points and _points_close(result_points[-1], end_point):
            result_bulges[-1] = 0.0
        else:
            result_points.append(end_point)
            result_bulges.append(0.0)

    if len(result_points) >= 2 and _points_close(result_points[0], result_points[-1]):
        result_points.pop()
        result_bulges.pop()

    return result_points, result_bulges


def _polygon_area(points: Sequence[Tuple[float, float]]) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _points_close(a: Tuple[float, float], b: Tuple[float, float], tol: float = 1e-9) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


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
