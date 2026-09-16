"""Generate door list report from resolved room objects."""

from __future__ import annotations
from ..models.room import ResolvedObject
from ..parametric.face_layout import calculate_face_layout


def build_door_list(objects: list[ResolvedObject]) -> list[dict]:
    """
    One row per door face with computed width and height.
    """
    doors = []
    for obj in objects:
        if "cabinet" not in obj.object_type or obj.door_count <= 0:
            continue

        toe_kick = obj.toe_kick_height if obj.object_type != "wall_cabinet" else 0
        layout = calculate_face_layout(obj, obj.z + toe_kick)

        for door in layout.doors:
            doors.append({
                "object_id": obj.object_id,
                "object_type": obj.object_type,
                "door_index": door.index,
                "width": round(door.width, 4),
                "height": round(door.height, 4),
                "hinge_side": door.hinge_side,
            })

    return doors
