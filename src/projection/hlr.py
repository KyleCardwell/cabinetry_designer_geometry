"""Hidden-line removal for elevations (SPEC-41): flat rectangles at a depth, nearer hides farther."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon
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
    opaque: bool = True         # hides what's behind it; an outline (recess, opening, soffit) doesn't (SPEC-42.1)
    outlined: bool = True       # draws the polygon's boundary; False draws only `lines` (SPEC-42.1)
    group: str | None = None    # optional part id for accessory-to-accessory occlusion
    group_front: float = 0      # nearer within the group, independent of room depth
    group_opaque: bool = False  # hides deeper members of this group only
    strips: tuple = ()          # ((z1, z2, front), ...): hides and is hidden per horizontal strip (SPEC-D7)


def _is_nearer(other: HlrShape, shape: HlrShape) -> bool:
    return (other.opaque and other.front > shape.front + EPSILON) or (
        shape.group is not None and other.group == shape.group and other.group_opaque
        and other.group_front > shape.group_front + EPSILON
    )


def _zones(shape: HlrShape):
    """(box, front) per zone of `shape`: its strips across its x range +-1", else the whole plane."""
    if not shape.strips or shape.polygon.is_empty:
        return [(None, shape.front)]
    x0, bottom, x1, top = shape.polygon.bounds
    zones = []
    for index, (z1, z2, front) in enumerate(shape.strips):
        if index == 0:
            z1 = bottom - 1
        if index == len(shape.strips) - 1:
            z2 = top + 1
        zones.append((Polygon([(x0 - 1, z1), (x1 + 1, z1), (x1 + 1, z2), (x0 - 1, z2)]), front))
    return zones


def _polygonal(geom):
    """Keep only polygon parts with area: touching strip boundaries hide nothing."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return geom if geom.area > EPSILON else None
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        polygons = []
        for part in geom.geoms:
            polygonal = _polygonal(part)
            if isinstance(polygonal, Polygon):
                polygons.append(polygonal)
            elif isinstance(polygonal, MultiPolygon):
                polygons.extend(polygonal.geoms)
        if polygons:
            return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    return None


def _nearer_cells(other: HlrShape, shape: HlrShape, front: float):
    """The polygon of `other` that counts as nearer than `front` (None when none), SPEC-D7."""
    if shape.group is not None and other.group == shape.group and other.group_opaque \
            and other.group_front > shape.group_front + EPSILON:
        return _polygonal(other.polygon)
    if not other.opaque:
        return None
    if not other.strips or other.polygon.is_empty:
        return _polygonal(other.polygon) if other.front > front + EPSILON else None
    near = [box for box, f in _zones(other) if f > front + EPSILON]
    if not near:
        return None
    if len(near) == len(other.strips):
        return _polygonal(other.polygon)
    cells = [_polygonal(other.polygon.intersection(box)) for box in near]
    return _polygonal(unary_union([cell for cell in cells if cell is not None]))


def _strip_cover(shapes: list[HlrShape], shape: HlrShape, dashing: bool = False):
    """covered(S): union over S's zones of the zone box and the nearer cells, or None."""
    pieces = []
    for box, front in _zones(shape):
        cells = []
        for other in shapes:
            if other is shape:
                continue
            cell = _nearer_cells(other, shape, front)
            if cell is None or cell.is_empty:
                continue
            if dashing and shape.is_box and other.covers_box_edges:
                continue
            cells.append(cell)
        if not cells:
            continue
        union = unary_union(cells)
        piece = _polygonal(union if box is None else union.intersection(box))
        if piece is not None:
            pieces.append(piece)
    return _polygonal(unary_union(pieces)) if pieces else None


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


def visible_regions(shapes: list[HlrShape], ids: set[str]) -> dict[str, object]:
    """For each shape whose id is in `ids`: the part of its polygon no nearer opaque shape covers (SPEC-42.2)."""
    regions = {}
    striped = any(shape.strips for shape in shapes)
    for shape in shapes:
        if shape.id not in ids:
            continue
        if striped:
            covered = _strip_cover(shapes, shape)
            regions[shape.id] = shape.polygon if covered is None else shape.polygon.difference(covered)
            continue
        nearer = [other.polygon for other in shapes if _is_nearer(other, shape)]
        regions[shape.id] = shape.polygon.difference(unary_union(nearer)) if nearer else shape.polygon
    return regions


def hidden_line_removal(shapes: list[HlrShape]) -> dict[str, tuple[list[Line2D], list[Line2D]]]:
    """For each shape id: (visible, hidden) segments of its outline (exterior and hole rings)."""
    result = {}
    striped = any(shape.strips for shape in shapes)
    for shape in shapes:
        drawn = [shape.polygon.boundary] if shape.outlined else []
        drawn.extend(LineString(line) for line in shape.lines)
        if not drawn:
            result[shape.id] = ([], [])
            continue
        # Grouped loops keep their source segments: unioning touching rod and
        # bracket lines would split one bracket side into several DXF LINEs.
        edges = drawn if shape.group is not None else [
            drawn[0] if len(drawn) == 1 else unary_union(drawn)
        ]
        if striped:
            covered = _strip_cover(shapes, shape)
            if covered is None:
                result[shape.id] = ([line for edge in edges for line in _geometry_to_lines(edge)], [])
                continue
            visible = [line for edge in edges for line in _geometry_to_lines(edge.difference(covered))]
            union = None if shape.drop_hidden else _strip_cover(shapes, shape, dashing=True)
            hidden_lines = []
            if union is not None:
                hidden_lines = [line for edge in edges
                                for line in _geometry_to_lines(edge.intersection(union).difference(union.boundary))]
            result[shape.id] = (visible, hidden_lines)
            continue
        nearer = [other for other in shapes if _is_nearer(other, shape)]
        if not nearer:
            result[shape.id] = ([line for edge in edges for line in _geometry_to_lines(edge)], [])
            continue

        covered = unary_union([other.polygon for other in nearer])
        visible = [line for edge in edges for line in _geometry_to_lines(edge.difference(covered))]
        dashing = [] if shape.drop_hidden else [
            other.polygon for other in nearer
            if not (shape.is_box and other.covers_box_edges)
        ]
        hidden_lines = []
        if dashing:
            union = unary_union(dashing)
            hidden_lines = [line for edge in edges
                            for line in _geometry_to_lines(edge.intersection(union).difference(union.boundary))]
        result[shape.id] = (visible, hidden_lines)
    return result
