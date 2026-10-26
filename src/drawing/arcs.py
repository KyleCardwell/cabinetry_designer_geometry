"""Flatten bulged outlines for geometry and recover their circular DXF edges."""

from dataclasses import dataclass, replace
from math import asin, atan, atan2, ceil, cos, hypot, pi, sin, sqrt

from src.models.geometry import Line2D


# Use a tighter sagitta than the 0.001-inch maximum so even clipped chord
# endpoints satisfy the 1e-5-inch radial tolerance used to recover arcs.
SAGITTA = 1e-6
ARC_TOLERANCE = 1e-5
OutlinePoint = tuple[float, float] | tuple[float, float, float]


@dataclass(frozen=True)
class OutlineArc:
    center: tuple[float, float]
    radius: float
    start_angle: float  # radians, in the source outline's walking direction
    end_angle: float
    ccw: bool

    @property
    def sweep(self) -> float:
        return (self.end_angle - self.start_angle) * (1 if self.ccw else -1)

    def progress(self, x: float, y: float) -> float:
        """Angle along the source sweep, independent of how HLR orders lines."""
        angle = atan2(y - self.center[1], x - self.center[0])
        progress = ((angle - self.start_angle) * (1 if self.ccw else -1)) % (2 * pi)
        if 2 * pi - progress <= ARC_TOLERANCE / self.radius:
            return 0.0
        return progress


def flatten_outline(
    outline: list[OutlinePoint], closed: bool = True,
) -> tuple[list[tuple[float, float]], list[OutlineArc]]:
    """Preserve straight vertices and source arcs, closing only when requested.

    Include arc extrema so the flattened bounds also capture bulges between
    supplied vertices. Two-number points retain their original straight edges.
    """
    points = []
    arcs = []
    for index, point in enumerate(outline):
        x, y = point[:2]
        points.append((x, y))
        if not closed and index == len(outline) - 1:
            break
        end_x, end_y = outline[(index + 1) % len(outline)][:2]
        bulge = point[2] if len(point) == 3 else 0.0
        if not bulge:
            continue
        dx, dy = end_x - x, end_y - y
        chord = hypot(dx, dy)
        if not chord:
            raise ValueError("A bulged outline segment must have distinct endpoints")
        factor = (1 - bulge * bulge) / (4 * bulge)
        center = ((x + end_x) / 2 - dy * factor, (y + end_y) / 2 + dx * factor)
        radius = chord * (1 + bulge * bulge) / (4 * abs(bulge))
        start = atan2(y - center[1], x - center[0])
        sweep = 4 * atan(bulge)
        arc = OutlineArc(center, radius, start, start + sweep, bulge > 0)
        arcs.append(arc)
        # 4*asin(...) avoids cancellation for a very large radius.
        step = 4 * asin(sqrt(min(SAGITTA / (2 * radius), 1.0)))
        count = max(1, ceil(abs(sweep) / step))
        progress = {abs(sweep) * i / count for i in range(1, count)}
        for angle in (0, pi / 2, pi, 3 * pi / 2):
            distance = ((angle - start) * (1 if arc.ccw else -1)) % (2 * pi)
            if 0 < distance < abs(sweep):
                progress.add(distance)
        for distance in sorted(progress):
            angle = start + distance * (1 if arc.ccw else -1)
            points.append((center[0] + radius * cos(angle), center[1] + radius * sin(angle)))
    return points, arcs


def rejoin_arcs(lines: list[Line2D], sources: list[OutlineArc]) -> tuple[list[Line2D], list[OutlineArc]]:
    """Recover one arc per uninterrupted stretch, preserving all other lines.

    HLR can reorder or reverse segments. Sort their intervals along each source
    sweep before merging; never bridge an actual gap. A midpoint check keeps a
    straight detail chord from being mistaken for the source's curved edge.
    """
    if not sources:
        return lines, []
    straight = []
    intervals = [[] for _ in sources]
    for line in lines:
        endpoints = [(line.start.x, line.start.y), (line.end.x, line.end.y)]
        midpoint = ((line.start.x + line.end.x) / 2, (line.start.y + line.end.y) / 2)
        for index, arc in enumerate(sources):
            if any(abs(hypot(x - arc.center[0], y - arc.center[1]) - arc.radius) > ARC_TOLERANCE
                   for x, y in [*endpoints, midpoint]):
                continue
            start, end = sorted(arc.progress(x, y) for x, y in endpoints)
            if end > arc.sweep + ARC_TOLERANCE / arc.radius:
                continue
            intervals[index].append((start, min(end, arc.sweep)))
            break
        else:
            straight.append(line)
    recovered = []
    for arc, stretches in zip(sources, intervals):
        merged = []
        for start, end in sorted(stretches):
            if merged and (start - merged[-1][1]) * arc.radius <= 1e-8:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        direction = 1 if arc.ccw else -1
        recovered.extend(replace(arc, start_angle=arc.start_angle + start * direction,
                                 end_angle=arc.start_angle + end * direction)
                         for start, end in merged)
    return straight, recovered
