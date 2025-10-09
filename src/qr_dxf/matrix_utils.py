"""Utilities for working with QR code matrices."""

from __future__ import annotations

from typing import Sequence, Set, Tuple

Coordinate = Tuple[int, int]


def detect_quiet_zone(matrix: Sequence[Sequence[bool]]) -> int:
    """Return the size of the quiet zone around ``matrix``.

    The quiet zone is inferred by finding the minimum x/y coordinate that
    contains an active module. This assumes the matrix includes the quiet zone
    padding (which is the default for QR libraries).
    """

    size = len(matrix)
    if size == 0:
        return 0

    min_x = size
    min_y = size
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            if value:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
    if min_x == size or min_y == size:
        return 0
    return min(min_x, min_y)


def finder_pattern_modules(
    matrix: Sequence[Sequence[bool]],
) -> Tuple[Set[Coordinate], Set[Coordinate]]:
    """Return sets of coordinates for the finder pattern frame and eye modules.

    The first set contains the outer frame modules, and the second contains the
    inner "eye" modules. Coordinates are provided as ``(x, y)`` tuples using the
    same orientation as the provided matrix.
    """

    size = len(matrix)
    if size < 7:
        return set(), set()

    quiet_zone = detect_quiet_zone(matrix)
    frame: Set[Coordinate] = set()
    eyes: Set[Coordinate] = set()

    origins = [
        (quiet_zone, quiet_zone),
        (size - quiet_zone - 7, quiet_zone),
        (quiet_zone, size - quiet_zone - 7),
    ]

    for origin_x, origin_y in origins:
        if origin_x < 0 or origin_y < 0:
            continue
        if origin_x + 7 > size or origin_y + 7 > size:
            continue
        for dy in range(7):
            for dx in range(7):
                x = origin_x + dx
                y = origin_y + dy
                if not matrix[y][x]:
                    continue
                if 2 <= dx <= 4 and 2 <= dy <= 4:
                    eyes.add((x, y))
                else:
                    frame.add((x, y))

    return frame, eyes

