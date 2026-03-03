"""
Write floorplan projection data to a DXF document.
"""

from __future__ import annotations
from ..models.geometry import Line2D
from .writer import create_dxf_document, write_lines_to_layer, add_text, doc_to_bytes


def build_floorplan_dxf(
    floorplan_layers: dict[str, list[Line2D]],
    room_name: str = "",
) -> bytes:
    """
    Build a complete floorplan DXF from projected line layers.

    Args:
        floorplan_layers: Dict of layer_name → list of Line2D from floorplan.generate_floorplan().
        room_name: Optional room name for the title block.

    Returns:
        DXF file as bytes.
    """
    doc = create_dxf_document()

    for layer_name, lines in floorplan_layers.items():
        if lines:
            write_lines_to_layer(doc, layer_name, lines)

    if room_name:
        add_text(doc, f"FLOOR PLAN — {room_name}", x=0, y=-20, height=4)

    return doc_to_bytes(doc)
