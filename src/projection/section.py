"""
Section view generation (cut-plane through cabinets).

Milestone 3+ feature — stub for now with the core algorithm outlined.
A section view slices through primitives at a given cut plane,
hatches the cut solids, and projects beyond-plane geometry with HLR.
"""

from __future__ import annotations
from ..models.geometry import BoxPrimitive, Line2D, Point2D


def generate_section_view(
    boxes: list[BoxPrimitive],
    cut_x: float,
    view_direction: str = "positive_y",
) -> dict[str, list[Line2D]]:
    """
    Generate a section view at cut_x along the wall.

    Args:
        boxes: Wall-local BoxPrimitives.
        cut_x: X position of the cut plane (along wall).
        view_direction: Which side we're looking from.

    Returns:
        Dict with 'cut_lines' (hatched), 'visible', 'hidden'.
    """
    cut_lines: list[Line2D] = []
    beyond_boxes: list[BoxPrimitive] = []

    for box in boxes:
        x0 = box.origin.x
        x1 = box.origin.x + box.size.x

        if x0 <= cut_x <= x1:
            # Box is cut — generate cross-section rectangle in Y-Z plane
            y0 = box.origin.y
            y1 = box.origin.y + box.size.y
            z0 = box.origin.z
            z1 = box.origin.z + box.size.z

            # Section rectangle (Y horizontal, Z vertical in section view)
            cut_lines.extend([
                Line2D(start=Point2D(x=y0, y=z0), end=Point2D(x=y1, y=z0)),
                Line2D(start=Point2D(x=y1, y=z0), end=Point2D(x=y1, y=z1)),
                Line2D(start=Point2D(x=y1, y=z1), end=Point2D(x=y0, y=z1)),
                Line2D(start=Point2D(x=y0, y=z1), end=Point2D(x=y0, y=z0)),
            ])
        elif x0 > cut_x:
            # Box is beyond the cut plane — will be projected with HLR later
            beyond_boxes.append(box)

    # TODO: Run HLR on beyond_boxes projected onto Y-Z plane
    # For now, return just the cut lines
    return {
        "cut_lines": cut_lines,
        "visible": [],
        "hidden": [],
    }
