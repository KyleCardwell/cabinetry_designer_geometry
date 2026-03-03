"""
Core DXF document builder using ezdxf.

Manages layer creation, line styles, and provides helpers
for writing Line2D segments to named layers.
"""

from __future__ import annotations
import ezdxf
from ezdxf.document import Drawing
from ..models.geometry import Line2D


# Standard layer definitions: (name, color_index, linetype)
# AutoCAD Color Index: 7=white, 1=red, 2=yellow, 3=green, 4=cyan, 5=blue, 6=magenta
LAYER_DEFS = {
    "WALLS":          (7, "CONTINUOUS"),
    "WALLS-CENTER":   (8, "CENTER"),
    "CABINETS-BASE":  (3, "CONTINUOUS"),
    "CABINETS-WALL":  (4, "CONTINUOUS"),
    "CABINETS-TALL":  (5, "CONTINUOUS"),
    "APPLIANCES":     (1, "CONTINUOUS"),
    "FILLERS":        (6, "CONTINUOUS"),
    "ELEVATION-VISIBLE": (7, "CONTINUOUS"),
    "ELEVATION-HIDDEN":  (8, "DASHED"),
    "SECTION-CUT":    (1, "CONTINUOUS"),
    "DIMENSIONS":     (2, "CONTINUOUS"),
    "TEXT":           (7, "CONTINUOUS"),
}


def create_dxf_document() -> Drawing:
    """Create a new DXF document with standard layers and linetypes."""
    doc = ezdxf.new("R2010")

    # Ensure linetypes exist
    if "CENTER" not in doc.linetypes:
        doc.linetypes.add(
            "CENTER",
            pattern=[1.25, 0.75, -0.125, 0.125, -0.125],
            description="Center ____ _ ____ _ ____",
        )
    if "DASHED" not in doc.linetypes:
        doc.linetypes.add(
            "DASHED",
            pattern=[0.75, 0.5, -0.25],
            description="Dashed ---- ---- ----",
        )

    # Create layers
    for layer_name, (color, linetype) in LAYER_DEFS.items():
        doc.layers.add(layer_name, color=color, linetype=linetype)

    return doc


def write_lines_to_layer(
    doc: Drawing,
    layer_name: str,
    lines: list[Line2D],
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> None:
    """Write a list of Line2D segments to a named layer in modelspace."""
    msp = doc.modelspace()
    for line in lines:
        msp.add_line(
            (line.start.x + offset_x, line.start.y + offset_y),
            (line.end.x + offset_x, line.end.y + offset_y),
            dxfattribs={"layer": layer_name},
        )


def add_text(
    doc: Drawing,
    text: str,
    x: float,
    y: float,
    height: float = 3.0,
    layer: str = "TEXT",
) -> None:
    """Add a text entity to the DXF."""
    msp = doc.modelspace()
    msp.add_text(
        text,
        dxfattribs={
            "layer": layer,
            "height": height,
            "insert": (x, y),
        },
    )


def doc_to_bytes(doc: Drawing) -> bytes:
    """Serialize a DXF document to bytes."""
    import io
    stream = io.BytesIO()
    doc.write(stream)
    return stream.getvalue()
