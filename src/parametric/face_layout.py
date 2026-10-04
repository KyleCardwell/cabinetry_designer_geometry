"""Calculate cabinet face sizes and positions from resolved parameters."""

from __future__ import annotations

from dataclasses import dataclass

from ..models.room import ResolvedObject


@dataclass(frozen=True)
class FaceRectangle:
    index: int
    x: float
    z: float
    width: float
    height: float
    hinge_side: str | None = None


@dataclass(frozen=True)
class FaceLayout:
    drawer_fronts: tuple[FaceRectangle, ...]
    doors: tuple[FaceRectangle, ...]


def calculate_face_layout(obj: ResolvedObject, case_bottom: float) -> FaceLayout:
    """Lay out top-down drawer fronts followed by doors in the remaining space.

    Positive exterior reveals move a face inside the cabinet-box boundary;
    negative values produce an overlay beyond that boundary. Legacy
    ``door_overlay`` and ``reveal_gap`` values remain supported when the new
    explicit reveal fields are omitted.
    """
    top_reveal = _outer_reveal(obj.face_top_reveal, obj.door_overlay)
    bottom_reveal = _outer_reveal(obj.face_bottom_reveal, obj.door_overlay)
    left_reveal = _outer_reveal(obj.face_left_reveal, obj.door_overlay)
    right_reveal = _outer_reveal(obj.face_right_reveal, obj.door_overlay)
    horizontal_reveal = _internal_reveal(
        obj.face_horizontal_reveal, obj.reveal_gap
    )
    vertical_reveal = _internal_reveal(obj.face_vertical_reveal, obj.reveal_gap)

    face_x = left_reveal
    face_width = obj.width - left_reveal - right_reveal
    if face_width <= 0:
        raise ValueError("Face left/right reveals leave no usable face width")

    heights = obj.drawer_heights or [6.0] * obj.drawer_count
    if len(heights) != obj.drawer_count:
        raise ValueError("drawer_heights length must match drawer_count")

    case_top = obj.z + obj.height
    current_top = case_top - top_reveal
    drawer_fronts: list[FaceRectangle] = []

    for index, height in enumerate(heights):
        if height <= 0:
            raise ValueError("Drawer front heights must be positive")
        front_z = current_top - height
        drawer_fronts.append(FaceRectangle(
            index=index,
            x=face_x,
            z=front_z,
            width=face_width,
            height=height,
        ))
        current_top = front_z - horizontal_reveal

    doors: list[FaceRectangle] = []
    if obj.door_count > 0:
        door_bottom = case_bottom + bottom_reveal
        door_height = current_top - door_bottom
        if door_height <= 0:
            raise ValueError("Face reveals and drawer fronts leave no room for doors")

        total_vertical_reveal = (obj.door_count - 1) * vertical_reveal
        door_width = (face_width - total_vertical_reveal) / obj.door_count
        if door_width <= 0:
            raise ValueError("Vertical reveals leave no usable door width")

        for index in range(obj.door_count):
            hinge = (
                obj.hinge_side
                if obj.door_count == 1
                else ("left" if index == 0 else "right")
            )
            doors.append(FaceRectangle(
                index=index,
                x=face_x + index * (door_width + vertical_reveal),
                z=door_bottom,
                width=door_width,
                height=door_height,
                hinge_side=hinge,
            ))

    return FaceLayout(drawer_fronts=tuple(drawer_fronts), doors=tuple(doors))


def _outer_reveal(explicit_reveal: float | None, legacy_overlay: float) -> float:
    if explicit_reveal is not None:
        return explicit_reveal
    return -legacy_overlay


def _internal_reveal(explicit_reveal: float | None, legacy_gap: float) -> float:
    if explicit_reveal is not None:
        return explicit_reveal
    return legacy_gap
