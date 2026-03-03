"""
Hidden Line Removal for wall elevation views.

Strategy for axis-aligned cabinet boxes:
1. Front-project each box onto the elevation plane (discard depth axis).
2. Depth-sort boxes front-to-back.
3. For each box's projected edges, clip against the union of all
   projected faces of boxes in front using Shapely difference().
4. Visible segments → solid lines; fully occluded → omit or dashed.

This is O(n²) in box count, but cabinets per wall rarely exceed ~20.
"""

from __future__ import annotations
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.ops import unary_union
from ..models.geometry import BoxPrimitive, Line2D, Point2D


def _box_to_elevation_rect(box: BoxPrimitive) -> tuple[Polygon, float]:
    """
    Project a BoxPrimitive onto the XZ plane (elevation view).
    Returns (2D polygon in X-Z space, depth_y for sorting).

    In wall-local coords:
      X = along wall → elevation X
      Z = up from floor → elevation Y
      Y = into room → depth (used for occlusion sorting)
    """
    x0 = box.origin.x
    x1 = box.origin.x + box.size.x
    z0 = box.origin.z
    z1 = box.origin.z + box.size.z

    rect = Polygon([
        (x0, z0), (x1, z0), (x1, z1), (x0, z1),
    ])

    # Depth: front face of the box (smaller Y = closer to viewer)
    depth = box.origin.y

    return rect, depth


def _polygon_to_lines(poly: Polygon) -> list[Line2D]:
    """Convert a Shapely polygon exterior to Line2D segments."""
    coords = list(poly.exterior.coords)
    lines = []
    for i in range(len(coords) - 1):
        lines.append(Line2D(
            start=Point2D(x=coords[i][0], y=coords[i][1]),
            end=Point2D(x=coords[i + 1][0], y=coords[i + 1][1]),
        ))
    return lines


def _geometry_to_lines(geom) -> list[Line2D]:
    """Convert any Shapely geometry to Line2D segments."""
    lines = []
    if geom.is_empty:
        return lines
    if isinstance(geom, Polygon):
        lines.extend(_polygon_to_lines(geom))
        for interior in geom.interiors:
            coords = list(interior.coords)
            for i in range(len(coords) - 1):
                lines.append(Line2D(
                    start=Point2D(x=coords[i][0], y=coords[i][1]),
                    end=Point2D(x=coords[i + 1][0], y=coords[i + 1][1]),
                ))
    elif isinstance(geom, MultiPolygon):
        for p in geom.geoms:
            lines.extend(_geometry_to_lines(p))
    elif isinstance(geom, (LineString, MultiLineString)):
        if isinstance(geom, LineString):
            coords = list(geom.coords)
            for i in range(len(coords) - 1):
                lines.append(Line2D(
                    start=Point2D(x=coords[i][0], y=coords[i][1]),
                    end=Point2D(x=coords[i + 1][0], y=coords[i + 1][1]),
                ))
        else:
            for ls in geom.geoms:
                lines.extend(_geometry_to_lines(ls))
    elif hasattr(geom, 'geoms'):
        for g in geom.geoms:
            lines.extend(_geometry_to_lines(g))
    return lines


def compute_hlr(boxes: list[BoxPrimitive]) -> tuple[list[Line2D], list[Line2D]]:
    """
    Perform hidden line removal on a list of box primitives for elevation view.

    Args:
        boxes: BoxPrimitives in wall-local coordinates.

    Returns:
        (visible_lines, hidden_lines) — both as Line2D in elevation (X, Z) space.
    """
    if not boxes:
        return [], []

    # Project all boxes and sort by depth (front first)
    projected: list[tuple[BoxPrimitive, Polygon, float]] = []
    for box in boxes:
        rect, depth = _box_to_elevation_rect(box)
        if rect.is_valid and not rect.is_empty:
            projected.append((box, rect, depth))

    # Sort front-to-back (smallest depth first)
    projected.sort(key=lambda item: item[2])

    visible_lines: list[Line2D] = []
    hidden_lines: list[Line2D] = []

    # Accumulate the union of all faces in front
    occluder_union: Polygon | MultiPolygon | None = None

    for box, rect, depth in projected:
        if occluder_union is None:
            # First (frontmost) box — fully visible
            visible_lines.extend(_polygon_to_lines(rect))
        else:
            # Clip this box's outline against what's in front
            try:
                visible_part = rect.difference(occluder_union)
                hidden_part = rect.intersection(occluder_union)

                visible_lines.extend(_geometry_to_lines(visible_part))
                hidden_lines.extend(_geometry_to_lines(hidden_part))
            except Exception:
                # Fallback: treat as fully visible if geometry ops fail
                visible_lines.extend(_polygon_to_lines(rect))

        # Add this box's face to the occluder union
        if occluder_union is None:
            occluder_union = rect
        else:
            try:
                occluder_union = unary_union([occluder_union, rect])
            except Exception:
                pass

    return visible_lines, hidden_lines
