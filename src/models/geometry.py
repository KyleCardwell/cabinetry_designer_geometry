"""Core geometry primitives used throughout the engine."""

from __future__ import annotations
from pydantic import BaseModel


class Point2D(BaseModel):
    x: float
    y: float


class Point3D(BaseModel):
    x: float
    y: float
    z: float


class Line2D(BaseModel):
    start: Point2D
    end: Point2D


class BoundingBox3D(BaseModel):
    """Axis-aligned 3D bounding box defined by origin + size."""
    origin: Point3D  # min corner
    size: Point3D    # width (x), depth (y), height (z)

    @property
    def max_corner(self) -> Point3D:
        return Point3D(
            x=self.origin.x + self.size.x,
            y=self.origin.y + self.size.y,
            z=self.origin.z + self.size.z,
        )

    @property
    def center(self) -> Point3D:
        return Point3D(
            x=self.origin.x + self.size.x / 2,
            y=self.origin.y + self.size.y / 2,
            z=self.origin.z + self.size.z / 2,
        )


class BoxPrimitive(BaseModel):
    """
    A single axis-aligned box representing a cabinet component.
    All dimensions in inches, positioned in wall-local coordinates:
      X = along wall, Y = into room (depth), Z = up from floor.
    """
    label: str          # e.g. 'left_side', 'right_side', 'bottom', 'top', 'back',
                        #      'shelf_1', 'door_left', 'drawer_front_1', 'toe_kick'
    origin: Point3D
    size: Point3D       # (width_x, depth_y, height_z)
    material: str       # e.g. 'plywood_3/4', 'plywood_1/4', 'solid'
    parent_object_id: str
    component_type: str # 'case', 'door', 'drawer_front', 'drawer_box', 'shelf',
                        # 'back', 'toe_kick', 'stretcher', 'filler'
