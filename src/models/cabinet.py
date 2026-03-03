"""Cabinet-specific parameter models for the geometry engine."""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class CabinetParams(BaseModel):
    """Fully resolved cabinet construction parameters."""
    width: float
    height: float
    depth: float
    material_thickness: float
    back_material_thickness: float
    toe_kick_height: float
    toe_kick_depth: float
    has_stretchers: bool
    shelf_count: int
    shelf_setback: float


class DoorParams(BaseModel):
    """Parameters for a single door."""
    width: float
    height: float
    overlay: float
    hinge_side: str  # 'left' | 'right'
    index: int


class DrawerParams(BaseModel):
    """Parameters for a single drawer (front + box)."""
    front_width: float
    front_height: float
    box_width: float
    box_height: float
    box_depth: float
    overlay: float
    slide_clearance: float
    index: int
