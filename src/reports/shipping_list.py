"""Generate shipping list report from resolved room objects."""

from __future__ import annotations
from ..models.room import ResolvedObject


def build_shipping_list(objects: list[ResolvedObject]) -> list[dict]:
    """
    One row per cabinet with key dimensions and face config.
    """
    rows = []
    item_num = 0
    for obj in objects:
        if "cabinet" not in obj.object_type:
            continue
        item_num += 1
        rows.append({
            "item": item_num,
            "object_id": obj.object_id,
            "type": obj.object_type,
            "width": obj.width,
            "height": obj.height,
            "depth": obj.depth,
            "door_count": obj.door_count,
            "drawer_count": obj.drawer_count,
            "hinge_side": obj.hinge_side,
            "shelf_count": obj.shelf_count,
        })
    return rows
