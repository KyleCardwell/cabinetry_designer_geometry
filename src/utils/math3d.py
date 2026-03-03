"""3D math utilities."""

from __future__ import annotations
import math


def distance_3d(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)


def box_volume(w: float, h: float, d: float) -> float:
    return w * h * d


def box_surface_area(w: float, h: float, d: float) -> float:
    return 2 * (w * h + w * d + h * d)
