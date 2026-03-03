"""Generate drawer front list report from resolved room objects."""

from __future__ import annotations
from ..models.room import ResolvedObject


def build_drawer_front_list(objects: list[ResolvedObject]) -> list[dict]:
    """
    One row per drawer front with computed width and height.
    """
    fronts = []
    for obj in objects:
        if not obj.drawer_count or obj.drawer_count <= 0:
            continue

        overlay = obj.door_overlay
        reveal = obj.reveal_gap
        front_w = obj.width + 2 * overlay
        heights = obj.drawer_heights or [6.0] * obj.drawer_count

        for i, dh in enumerate(heights):
            front_h = dh + 2 * overlay - (reveal if i > 0 else 0)
            fronts.append({
                "object_id": obj.object_id,
                "object_type": obj.object_type,
                "drawer_index": i,
                "width": round(front_w, 4),
                "height": round(front_h, 4),
            })

    return fronts
