"""Pydantic models for resolved room data received from the Node backend."""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class ResolvedWall(BaseModel):
    wall_id: str
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float
    height: float


class ResolvedObject(BaseModel):
    object_id: str
    object_type: str
    wall_id: Optional[str] = None
    x: float
    y: float
    z: float = 0.0
    rotation: float = 0.0

    # Fully resolved dimensions (no nulls)
    width: float
    height: float
    depth: float

    # Construction
    material_thickness: float
    back_material_thickness: float
    toe_kick_height: float
    toe_kick_depth: float
    has_stretchers: bool

    # Face
    door_count: int
    drawer_count: int
    door_overlay: float
    reveal_gap: float
    hinge_side: str

    # Drawers
    drawer_slide_clearance: float
    drawer_heights: Optional[list[float]] = None
    drawer_box_depth: Optional[float] = None

    # Shelves
    shelf_count: int
    shelf_setback: float


class ResolvedRoom(BaseModel):
    room_id: str
    name: str
    floor_to_ceiling: float
    walls: list[ResolvedWall]
    objects: list[ResolvedObject]
