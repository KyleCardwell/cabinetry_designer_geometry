"""Hidden-line removal for elevations (SPEC-41): flat rectangles at a depth, nearer hides farther."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from shapely.geometry import GeometryCollection, LineString, MultiLineString, Polygon
from shapely.ops import unary_union

from ..models.geometry import Line2D, Point2D

EPSILON = 1e-6


@dataclass(frozen=True)
class HlrShape:
    id: str
    polygon: Polygon
    front: float
    is_box: bool = False
    covers_box_edges: bool = False
    drop_hidden: bool = False   # hidden edges are left out, never dashed (SPEC-42)
    lines: tuple = ()           # detail lines inside the shape: ((x1, z1), (x2, z2)) pairs


def rect_polygon(x: float, z: float, width: float, height: float, holes=()) -> Polygon:
    """A rectangle, with each (x, z, width, height) in `holes` cut out of it."""
    def ring(x, z, width, height):
        return [(x, z), (x + width, z), (x + width, z + height), (x, z + height)]

    return Polygon(ring(x, z, width, height), [ring(*hole) for hole in holes])


def _geometry_to_lines(geometry) -> list[Line2D]:
    """Flatten line geometry, omitting segments shorter than EPSILON."""
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        coords = list(geometry.coords)
        return [
            Line2D(start=Point2D(x=x0, y=y0), end=Point2D(x=x1, y=y1))
            for (x0, y0), (x1, y1) in zip(coords, coords[1:])
            if hypot(x1 - x0, y1 - y0) >= EPSILON
        ]
    if isinstance(geometry, (MultiLineString, GeometryCollection)):
        return [line for part in geometry.geoms for line in _geometry_to_lines(part)]
    return []


def hidden_line_removal(shapes: list[HlrShape]) -> dict[str, tuple[list[Line2D], list[Line2D]]]:
    """For each shape id: (visible, hidden) segments of its outline (exterior and hole rings)."""
    result = {}
    for shape in shapes:
        edges = shape.polygon.boundary
        if shape.lines:
            edges = unary_union([edges, *(LineString(line) for line in shape.lines)])
        nearer = [other for other in shapes if other.front > shape.front + EPSILON]
        if not nearer:
            result[shape.id] = (_geometry_to_lines(edges), [])
            continue

        visible = edges.difference(unary_union([other.polygon for other in nearer]))
        dashing = [] if shape.drop_hidden else [
            other.polygon for other in nearer
            if not (shape.is_box and other.covers_box_edges)
        ]
        hidden_lines = []
        if dashing:
            union = unary_union(dashing)
            hidden_lines = _geometry_to_lines(edges.intersection(union).difference(union.boundary))
        result[shape.id] = (_geometry_to_lines(visible), hidden_lines)
    return result
