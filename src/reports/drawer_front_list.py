"""Generate drawer front list report from resolved room objects."""

from __future__ import annotations
from ..models.room import ResolvedObject
from ..parametric.face_layout import calculate_face_layout


def build_drawer_front_list(objects: list[ResolvedObject]) -> list[dict]:
    """
    One row per drawer front with computed width and height.
    """
    fronts = []
    for obj in objects:
        if not obj.drawer_count or obj.drawer_count <= 0:
            continue

        toe_kick = obj.toe_kick_height if obj.object_type != "wall_cabinet" else 0
        layout = calculate_face_layout(obj, obj.z + toe_kick)

        for front in layout.drawer_fronts:
            fronts.append({
                "object_id": obj.object_id,
                "object_type": obj.object_type,
                "drawer_index": front.index,
                "width": round(front.width, 4),
                "height": round(front.height, 4),
            })

    return fronts
