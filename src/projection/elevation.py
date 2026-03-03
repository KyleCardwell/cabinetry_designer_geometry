"""
Generate wall elevation views.

For each wall, gather all objects associated with that wall,
transform their box primitives to wall-local coordinates,
then run HLR to produce visible/hidden line sets.
"""

from __future__ import annotations
import math
from ..models.geometry import BoxPrimitive, Point3D, Line2D
from ..models.room import ResolvedRoom, ResolvedWall, ResolvedObject
from .hlr import compute_hlr


def _wall_transform_matrix(wall: ResolvedWall) -> tuple[float, float, float, float, float]:
    """
    Compute the transform from room coords to wall-local coords.
    Returns (cos, sin, wall_x1, wall_y1, wall_length).

    Wall-local: X along wall, Y perpendicular (into room), Z unchanged.
    """
    dx = wall.x2 - wall.x1
    dy = wall.y2 - wall.y1
    length = math.hypot(dx, dy)
    if length == 0:
        return 1.0, 0.0, wall.x1, wall.y1, 0.0
    cos_a = dx / length
    sin_a = dy / length
    return cos_a, sin_a, wall.x1, wall.y1, length


def _room_to_wall_local(
    rx: float, ry: float, cos_a: float, sin_a: float, wx1: float, wy1: float
) -> tuple[float, float]:
    """Transform a room-coordinate point to wall-local (along_wall, into_room)."""
    dx = rx - wx1
    dy = ry - wy1
    along = dx * cos_a + dy * sin_a
    perp = -dx * sin_a + dy * cos_a
    return along, perp


def transform_box_to_wall_local(
    box: BoxPrimitive,
    obj: ResolvedObject,
    cos_a: float,
    sin_a: float,
    wx1: float,
    wy1: float,
) -> BoxPrimitive:
    """
    Transform a box primitive from object-local to wall-local coordinates.

    Object-local origin is at (obj.x, obj.y) in room coords with obj.rotation.
    Wall-local: X along wall, Y into room, Z up.
    """
    # Object rotation
    obj_rad = math.radians(obj.rotation)
    obj_cos = math.cos(obj_rad)
    obj_sin = math.sin(obj_rad)

    # Transform box origin from object-local to room coords
    bx = box.origin.x
    by = box.origin.y
    room_x = obj.x + bx * obj_cos - by * obj_sin
    room_y = obj.y + bx * obj_sin + by * obj_cos

    # Room to wall-local
    wall_x, wall_y = _room_to_wall_local(room_x, room_y, cos_a, sin_a, wx1, wy1)

    # Rotate the size vector too (for non-zero object rotation relative to wall)
    # For axis-aligned cabinets snapped to walls, rotation is typically the wall angle,
    # so relative rotation is ~0. Handle the general case anyway.
    rel_angle = obj.rotation - math.degrees(math.atan2(sin_a, cos_a))
    rel_rad = math.radians(rel_angle)
    rel_cos = math.cos(rel_rad)
    rel_sin = math.sin(rel_rad)

    sx = abs(box.size.x * rel_cos) + abs(box.size.y * rel_sin)
    sy = abs(box.size.x * rel_sin) + abs(box.size.y * rel_cos)

    return BoxPrimitive(
        label=box.label,
        origin=Point3D(x=wall_x, y=wall_y, z=box.origin.z),
        size=Point3D(x=sx, y=sy, z=box.size.z),
        material=box.material,
        parent_object_id=box.parent_object_id,
        component_type=box.component_type,
    )


def generate_wall_elevation(
    wall: ResolvedWall,
    objects: list[ResolvedObject],
    object_boxes: dict[str, list[BoxPrimitive]],
) -> dict[str, list[Line2D]]:
    """
    Generate elevation lines for a single wall.

    Args:
        wall: The wall to generate an elevation for.
        objects: Objects associated with this wall.
        object_boxes: Dict mapping object_id → list of BoxPrimitive (object-local coords).

    Returns:
        Dict with keys 'visible' and 'hidden', each a list of Line2D in elevation (X, Z) space.
        X = position along wall (0 at wall start), Z = height from floor.
    """
    cos_a, sin_a, wx1, wy1, wall_length = _wall_transform_matrix(wall)

    # Collect all wall-local boxes
    all_wall_boxes: list[BoxPrimitive] = []

    for obj in objects:
        boxes = object_boxes.get(obj.object_id, [])
        for box in boxes:
            wall_box = transform_box_to_wall_local(box, obj, cos_a, sin_a, wx1, wy1)
            all_wall_boxes.append(wall_box)

    # Run HLR
    visible, hidden = compute_hlr(all_wall_boxes)

    return {
        "visible": visible,
        "hidden": hidden,
        "wall_length": wall_length,
        "wall_height": wall.height,
    }


def generate_all_elevations(
    room: ResolvedRoom,
    object_boxes: dict[str, list[BoxPrimitive]],
) -> dict[str, dict]:
    """
    Generate elevations for all walls in the room.

    Returns dict mapping wall_id → elevation result.
    """
    # Index objects by wall_id
    objects_by_wall: dict[str, list[ResolvedObject]] = {}
    for obj in room.objects:
        if obj.wall_id:
            objects_by_wall.setdefault(obj.wall_id, []).append(obj)

    elevations = {}
    for wall in room.walls:
        wall_objects = objects_by_wall.get(wall.wall_id, [])
        if wall_objects:
            elevations[wall.wall_id] = generate_wall_elevation(
                wall, wall_objects, object_boxes
            )

    return elevations
