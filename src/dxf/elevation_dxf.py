"""
Write wall elevation data to a DXF document.

Each wall elevation is placed in its own viewport region,
offset horizontally so multiple elevations appear side-by-side.
"""

from __future__ import annotations
from ..models.geometry import Line2D, Point2D
from .writer import create_dxf_document, write_lines_to_layer, add_text, doc_to_bytes


def build_elevation_dxf(
    elevations: dict[str, dict],
    room_name: str = "",
) -> bytes:
    """
    Build a DXF containing all wall elevations for a room.

    Args:
        elevations: Dict mapping wall_id → {visible, hidden, wall_length, wall_height}.
        room_name: Optional room name for the title block.

    Returns:
        DXF file as bytes.
    """
    doc = create_dxf_document()

    # Place each wall elevation side-by-side with a gap
    gap = 24.0  # inches between elevation views
    current_x = 0.0

    for wall_id, elev_data in elevations.items():
        visible = elev_data.get("visible", [])
        hidden = elev_data.get("hidden", [])
        wall_length = elev_data.get("wall_length", 0)
        wall_height = elev_data.get("wall_height", 96)

        # Write visible lines
        write_lines_to_layer(doc, "ELEVATION-VISIBLE", visible, offset_x=current_x)

        # Write hidden lines
        write_lines_to_layer(doc, "ELEVATION-HIDDEN", hidden, offset_x=current_x)

        # Wall boundary lines (floor + ceiling + sides)
        wall_boundary = [
            Line2D(start=Point2D(x=0, y=0), end=Point2D(x=wall_length, y=0)),
            Line2D(start=Point2D(x=wall_length, y=0), end=Point2D(x=wall_length, y=wall_height)),
            Line2D(start=Point2D(x=wall_length, y=wall_height), end=Point2D(x=0, y=wall_height)),
            Line2D(start=Point2D(x=0, y=wall_height), end=Point2D(x=0, y=0)),
        ]
        write_lines_to_layer(doc, "WALLS", wall_boundary, offset_x=current_x)

        # Wall label
        add_text(
            doc,
            f"WALL {wall_id[:8]}",
            x=current_x,
            y=wall_height + 6,
            height=3,
        )

        current_x += wall_length + gap

    if room_name:
        add_text(doc, f"ELEVATIONS — {room_name}", x=0, y=-20, height=4)

    return doc_to_bytes(doc)
