"""
Generate 2D floorplan projection (top-down, Z=0 plane).

Projects all wall outlines and cabinet footprints onto the XY plane.
No HLR needed — floorplan is a pure top-down orthographic view.
"""

from __future__ import annotations
import math
from ..models.geometry import BoxPrimitive, Line2D, Point2D
from ..models.room import ResolvedRoom, ResolvedWall, ResolvedObject


def project_wall_outline(wall: ResolvedWall) -> list[Line2D]:
    """
    Project a wall into its 2D outline (a rectangle from the two endpoints + thickness).
    Returns 4 lines forming the wall rectangle.
    """
    dx = wall.x2 - wall.x1
    dy = wall.y2 - wall.y1
    length = math.hypot(dx, dy)
    if length == 0:
        return []

    # Normal direction (perpendicular to wall, unit length)
    nx = -dy / length * (wall.thickness / 2)
    ny = dx / length * (wall.thickness / 2)

    # Four corners of the wall rectangle
    c1 = Point2D(x=wall.x1 + nx, y=wall.y1 + ny)
    c2 = Point2D(x=wall.x1 - nx, y=wall.y1 - ny)
    c3 = Point2D(x=wall.x2 - nx, y=wall.y2 - ny)
    c4 = Point2D(x=wall.x2 + nx, y=wall.y2 + ny)

    return [
        Line2D(start=c1, end=c4),  # outer edge
        Line2D(start=c4, end=c3),  # end cap
        Line2D(start=c3, end=c2),  # inner edge
        Line2D(start=c2, end=c1),  # start cap
    ]


def project_wall_centerline(wall: ResolvedWall) -> Line2D:
    """Return the wall centerline as a 2D line."""
    return Line2D(
        start=Point2D(x=wall.x1, y=wall.y1),
        end=Point2D(x=wall.x2, y=wall.y2),
    )


def project_object_footprint(
    obj: ResolvedObject, boxes: list[BoxPrimitive]
) -> list[Line2D]:
    """
    Project the outermost footprint of a placed object onto the XY plane.
    Uses the object's position and rotation to transform box origins to room coords.
    For simplicity in POC, uses the object's bounding rectangle (width × depth).
    """
    w = obj.width
    d = obj.depth
    rad = math.radians(obj.rotation)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)

    # Local corners (object centered at x, object back against wall at y)
    # Object origin: center-x at obj.x, back edge at obj.y
    local_corners = [
        (-w / 2, 0.0),
        (w / 2, 0.0),
        (w / 2, -d),
        (-w / 2, -d),
    ]

    # Transform to room coordinates
    room_corners = []
    for lx, ly in local_corners:
        rx = obj.x + lx * cos_r - ly * sin_r
        ry = obj.y + lx * sin_r + ly * cos_r
        room_corners.append(Point2D(x=rx, y=ry))

    # Build 4 edges
    lines = []
    for i in range(4):
        lines.append(Line2D(start=room_corners[i], end=room_corners[(i + 1) % 4]))

    return lines


def generate_floorplan(room: ResolvedRoom, object_boxes: dict[str, list[BoxPrimitive]]) -> dict[str, list[Line2D]]:
    """
    Generate all floorplan lines grouped by layer.

    Args:
        room: Resolved room data.
        object_boxes: Dict mapping object_id → list of BoxPrimitive from cabinet_builder.

    Returns:
        Dict of layer_name → list of Line2D.
    """
    layers: dict[str, list[Line2D]] = {
        "WALLS": [],
        "WALLS-CENTER": [],
        "CABINETS-BASE": [],
        "CABINETS-WALL": [],
        "CABINETS-TALL": [],
        "APPLIANCES": [],
        "FILLERS": [],
    }

    # Walls
    for wall in room.walls:
        layers["WALLS"].extend(project_wall_outline(wall))
        layers["WALLS-CENTER"].append(project_wall_centerline(wall))

    # Objects
    layer_map = {
        "base_cabinet": "CABINETS-BASE",
        "wall_cabinet": "CABINETS-WALL",
        "tall_cabinet": "CABINETS-TALL",
        "appliance": "APPLIANCES",
        "filler": "FILLERS",
    }

    for obj in room.objects:
        layer = layer_map.get(obj.object_type, "CABINETS-BASE")
        boxes = object_boxes.get(obj.object_id, [])
        layers[layer].extend(project_object_footprint(obj, boxes))

    return layers
