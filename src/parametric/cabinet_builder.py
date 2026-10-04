"""
Expand a resolved cabinet object into a list of BoxPrimitive components.

All geometry is in wall-local coordinates:
  X = along wall (0 at object center, or at object.x)
  Y = into room (0 at wall face)
  Z = up from floor (0 at floor)

The builder is purely deterministic: same inputs always produce same outputs.
"""

from __future__ import annotations
from ..models.geometry import BoxPrimitive, Point3D
from ..models.room import ResolvedObject
from .face_layout import FaceLayout, calculate_face_layout


def expand_cabinet(obj: ResolvedObject) -> list[BoxPrimitive]:
    """Expand a single resolved cabinet into box primitives."""
    if "cabinet" not in obj.object_type:
        return _expand_simple(obj)

    boxes: list[BoxPrimitive] = []
    mt = obj.material_thickness
    bmt = obj.back_material_thickness
    w = obj.width
    h = obj.height
    d = obj.depth
    tk_h = obj.toe_kick_height if obj.object_type != "wall_cabinet" else 0.0
    tk_d = obj.toe_kick_depth if obj.object_type != "wall_cabinet" else 0.0

    # Interior dimensions
    interior_w = w - 2 * mt
    interior_h = h - tk_h - mt  # floor of case to underside of top
    interior_d = d - bmt

    # Base Z for the cabinet case (above toe kick for base/tall, at obj.z for wall)
    case_z = obj.z + tk_h

    # --- Case sides ---
    boxes.append(BoxPrimitive(
        label="left_side",
        origin=Point3D(x=0.0, y=0.0, z=case_z),
        size=Point3D(x=mt, y=d, z=h - tk_h),
        material=f"plywood_{mt}",
        parent_object_id=obj.object_id,
        component_type="case",
    ))
    boxes.append(BoxPrimitive(
        label="right_side",
        origin=Point3D(x=w - mt, y=0.0, z=case_z),
        size=Point3D(x=mt, y=d, z=h - tk_h),
        material=f"plywood_{mt}",
        parent_object_id=obj.object_id,
        component_type="case",
    ))

    # --- Bottom ---
    boxes.append(BoxPrimitive(
        label="bottom",
        origin=Point3D(x=mt, y=0.0, z=case_z),
        size=Point3D(x=interior_w, y=d, z=mt),
        material=f"plywood_{mt}",
        parent_object_id=obj.object_id,
        component_type="case",
    ))

    # --- Top ---
    boxes.append(BoxPrimitive(
        label="top",
        origin=Point3D(x=mt, y=0.0, z=case_z + h - tk_h - mt),
        size=Point3D(x=interior_w, y=d, z=mt),
        material=f"plywood_{mt}",
        parent_object_id=obj.object_id,
        component_type="case",
    ))

    # --- Back ---
    boxes.append(BoxPrimitive(
        label="back",
        origin=Point3D(x=0.0, y=d - bmt, z=case_z),
        size=Point3D(x=w, y=bmt, z=h - tk_h),
        material=f"plywood_{bmt}",
        parent_object_id=obj.object_id,
        component_type="back",
    ))

    # --- Toe kick ---
    if tk_h > 0:
        boxes.append(BoxPrimitive(
            label="toe_kick",
            origin=Point3D(x=mt, y=0.0, z=obj.z),
            size=Point3D(x=interior_w, y=mt, z=tk_h),
            material=f"plywood_{mt}",
            parent_object_id=obj.object_id,
            component_type="toe_kick",
        ))

    # --- Stretchers ---
    if obj.has_stretchers and tk_h > 0:
        stretcher_z = obj.z + tk_h - mt
        # Front stretcher
        boxes.append(BoxPrimitive(
            label="stretcher_front",
            origin=Point3D(x=mt, y=0.0, z=stretcher_z),
            size=Point3D(x=interior_w, y=mt * 2, z=mt),
            material=f"plywood_{mt}",
            parent_object_id=obj.object_id,
            component_type="stretcher",
        ))
        # Back stretcher
        boxes.append(BoxPrimitive(
            label="stretcher_back",
            origin=Point3D(x=mt, y=d - bmt - mt * 2, z=stretcher_z),
            size=Point3D(x=interior_w, y=mt * 2, z=mt),
            material=f"plywood_{mt}",
            parent_object_id=obj.object_id,
            component_type="stretcher",
        ))

    # --- Shelves ---
    if obj.shelf_count > 0:
        shelf_zone_h = interior_h - mt  # between bottom and top panels
        spacing = shelf_zone_h / (obj.shelf_count + 1)
        for i in range(obj.shelf_count):
            shelf_z = case_z + mt + spacing * (i + 1)
            boxes.append(BoxPrimitive(
                label=f"shelf_{i + 1}",
                origin=Point3D(x=mt, y=obj.shelf_setback, z=shelf_z),
                size=Point3D(x=interior_w, y=interior_d - obj.shelf_setback, z=mt),
                material=f"plywood_{mt}",
                parent_object_id=obj.object_id,
                component_type="shelf",
            ))

    face_layout = calculate_face_layout(obj, case_z)

    # --- Doors ---
    boxes.extend(_build_doors(obj, face_layout, mt))

    # --- Drawers ---
    boxes.extend(_build_drawers(obj, face_layout, mt))

    return boxes


def _build_doors(
    obj: ResolvedObject, face_layout: FaceLayout, mt: float
) -> list[BoxPrimitive]:
    """Generate door box primitives for a cabinet."""
    boxes: list[BoxPrimitive] = []
    door_thickness = mt  # doors are material_thickness thick

    for door in face_layout.doors:
        boxes.append(BoxPrimitive(
            label=f"door_{door.hinge_side}_{door.index}",
            origin=Point3D(x=door.x, y=-door_thickness, z=door.z),
            size=Point3D(x=door.width, y=door_thickness, z=door.height),
            material="solid",
            parent_object_id=obj.object_id,
            component_type="door",
        ))

    return boxes


def _build_drawers(
    obj: ResolvedObject, face_layout: FaceLayout, mt: float
) -> list[BoxPrimitive]:
    """Generate drawer front + drawer box primitives."""
    boxes: list[BoxPrimitive] = []
    slide_clr = obj.drawer_slide_clearance
    box_w = obj.width - 2 * slide_clr
    box_d = obj.drawer_box_depth or (obj.depth - 3)

    for front in face_layout.drawer_fronts:
        # Drawer front
        boxes.append(BoxPrimitive(
            label=f"drawer_front_{front.index}",
            origin=Point3D(x=front.x, y=-mt, z=front.z),
            size=Point3D(x=front.width, y=mt, z=front.height),
            material="solid",
            parent_object_id=obj.object_id,
            component_type="drawer_front",
        ))

        # Drawer box
        box_h = front.height - mt
        box_z = front.z + mt / 2
        boxes.append(BoxPrimitive(
            label=f"drawer_box_{front.index}",
            origin=Point3D(x=slide_clr, y=0.0, z=box_z),
            size=Point3D(x=box_w, y=box_d, z=box_h),
            material=f"plywood_{mt}",
            parent_object_id=obj.object_id,
            component_type="drawer_box",
        ))

    return boxes


def _expand_simple(obj: ResolvedObject) -> list[BoxPrimitive]:
    """Expand a non-cabinet object (appliance, filler) as a single box."""
    return [
        BoxPrimitive(
            label=obj.object_type,
            origin=Point3D(x=0.0, y=0.0, z=obj.z),
            size=Point3D(x=obj.width, y=obj.depth, z=obj.height),
            material="solid",
            parent_object_id=obj.object_id,
            component_type=obj.object_type,
        )
    ]
