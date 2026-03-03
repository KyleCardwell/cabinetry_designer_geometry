"""2D math utilities."""

from __future__ import annotations
import math


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def angle_between(x1: float, y1: float, x2: float, y2: float) -> float:
    """Angle in radians from (x1,y1) to (x2,y2)."""
    return math.atan2(y2 - y1, x2 - x1)


def rotate_point(x: float, y: float, angle_rad: float, cx: float = 0, cy: float = 0) -> tuple[float, float]:
    """Rotate point (x,y) around (cx,cy) by angle_rad."""
    dx = x - cx
    dy = y - cy
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return (cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)


def line_intersection(
    x1: float, y1: float, x2: float, y2: float,
    x3: float, y3: float, x4: float, y4: float,
) -> tuple[float, float] | None:
    """
    Find intersection of line segments (x1,y1)-(x2,y2) and (x3,y3)-(x4,y4).
    Returns (x, y) or None if parallel/no intersection.
    """
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if 0 <= t <= 1 and 0 <= u <= 1:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return (ix, iy)
    return None
