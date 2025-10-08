"""DXF export helpers for QR modules."""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple


def qr_matrix_to_dxf(matrix: Sequence[Sequence[bool]], module_size: float = 1.0,
                     corner_radius: float = 0.0, layer: str = "QR") -> str:
    if module_size <= 0:
        raise ValueError("module_size must be positive")
    size = len(matrix)
    if size == 0:
        raise ValueError("matrix must not be empty")
    radius = max(0.0, min(corner_radius, module_size / 2))
    entities: List[str] = []
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            if value:
                entities.extend(_module_polyline(x, y, size, module_size, radius, layer))
    header = _dxf_header(layer)
    footer = _dxf_footer()
    return "\n".join(header + entities + footer) + "\n"


def _module_polyline(x: int, y: int, size: int, module: float, radius: float, layer: str) -> List[str]:
    x0 = x * module
    y0 = (size - y - 1) * module
    x1 = x0 + module
    y1 = y0 + module
    if radius <= 1e-9:
        points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        bulges = [0.0, 0.0, 0.0, 0.0]
    else:
        r = radius
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
