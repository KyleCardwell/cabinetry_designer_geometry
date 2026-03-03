"""Generate drawer box list report from resolved room objects."""

from __future__ import annotations
from ..models.room import ResolvedObject


def build_drawer_box_list(objects: list[ResolvedObject]) -> list[dict]:
    """
    One row per drawer box with computed width, height, and depth.
    """
    boxes = []
    for obj in objects:
        if not obj.drawer_count or obj.drawer_count <= 0:
            continue

        slide_clr = obj.drawer_slide_clearance
        mt = obj.material_thickness
        box_w = obj.width - 2 * slide_clr
        box_d = obj.drawer_box_depth or (obj.depth - 3)
        heights = obj.drawer_heights or [6.0] * obj.drawer_count

        for i, dh in enumerate(heights):
            box_h = dh - mt
            boxes.append({
                "object_id": obj.object_id,
                "object_type": obj.object_type,
                "drawer_index": i,
                "width": round(box_w, 4),
                "height": round(box_h, 4),
                "depth": round(box_d, 4),
            })

    return boxes
