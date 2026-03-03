"""Generate door list report from resolved room objects."""

from __future__ import annotations
from ..models.room import ResolvedObject


def build_door_list(objects: list[ResolvedObject]) -> list[dict]:
    """
    One row per door face with computed width and height.
    """
    doors = []
    for obj in objects:
        if "cabinet" not in obj.object_type or obj.door_count <= 0:
            continue

        drawer_total = sum(obj.drawer_heights or [])
        door_zone_h = obj.height - (
            obj.toe_kick_height if obj.object_type != "wall_cabinet" else 0
        ) - drawer_total

        overlay = obj.door_overlay
        reveal = obj.reveal_gap
        door_w = (obj.width + 2 * overlay - (obj.door_count - 1) * reveal) / obj.door_count
        door_h = door_zone_h + 2 * overlay

        for i in range(obj.door_count):
            hinge = (
                obj.hinge_side if obj.door_count == 1
                else ("left" if i == 0 else "right")
            )
            doors.append({
                "object_id": obj.object_id,
                "object_type": obj.object_type,
                "door_index": i,
                "width": round(door_w, 4),
                "height": round(door_h, 4),
                "hinge_side": hinge,
            })

    return doors
