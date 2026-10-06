"""
Core DXF document builder using ezdxf.

Manages layer creation, line styles, and provides helpers
for writing Line2D segments to named layers.
"""

from __future__ import annotations
import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from ..models.geometry import Line2D


# Standard layer definitions: (color_index, linetype, lineweight)
# AutoCAD Color Index: 7=white, 1=red, 2=yellow, 3=green, 4=cyan, 5=blue, 6=magenta
# Lineweights are in 1/100 mm (SPEC-43.1): walls heaviest, boxes and tops next, faces and parts medium,
# hidden lines, dimensions and text lightest.
LAYER_DEFS = {
    "WALLS":      (7, "CONTINUOUS", 50),
    "CABINETS":   (5, "CONTINUOUS", 35),
    "FACES":      (7, "CONTINUOUS", 25),
    "FILLERS":    (30, "CONTINUOUS", 25),
    "PANELS":     (6, "CONTINUOUS", 25),
    "FRAMES":     (3, "CONTINUOUS", 25),
    "SHELVES":    (4, "CONTINUOUS", 18),
    "COUNTERTOPS": (9, "CONTINUOUS", 35),
    "MOLDINGS":   (1, "CONTINUOUS", 25),
    "OPENINGS":   (40, "CONTINUOUS", 25),
    "SECTIONS":   (8, "CONTINUOUS", 25),
    "HIDDEN":     (8, "DASHED", 18),
    "DIMENSIONS": (2, "CONTINUOUS", 18),
    "TEXT":       (7, "CONTINUOUS", 18),
}

# Every label and dimension uses one text style (SPEC-43.1). The DXF names the font; the viewer supplies it.
TEXT_STYLE = "FF_TEXT"
TEXT_FONT = "arialn.ttf"
TEXT_FAMILY = "Arial Narrow"


def create_dxf_document() -> Drawing:
    """Create a new DXF document with standard layers and linetypes."""
    doc = ezdxf.new("R2010")
    doc.units = units.IN
    doc.header["$MEASUREMENT"] = 0  # English/imperial
    doc.header["$LUNITS"] = 4       # Architectural
    doc.header["$LUPREC"] = 4       # Display to 1/16 inch

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

    doc.header["$LWDISPLAY"] = 1    # show lineweights

    # Create layers
    for layer_name, (color, linetype, lineweight) in LAYER_DEFS.items():
        doc.layers.add(layer_name, color=color, linetype=linetype, lineweight=lineweight)

    style = doc.styles.new(TEXT_STYLE, dxfattribs={"font": TEXT_FONT})
    style.set_extended_font_data(family=TEXT_FAMILY, italic=False, bold=False)

    return doc


# The dimension style (SPEC-43). Sizes are paper inches; DIMSCALE (the plot scale) makes them drawing inches.
DIMSTYLE = "FF"
DIMSTYLE_PAPER = {
    "dimtxt": 0.09375,  # 3/32" text (SPEC-43.1)
    "dimtsz": 0.0625,   # architectural ticks, not arrows
    "dimexo": 0.0625,   # extension lines start 1/16" off the drawing
    "dimexe": 0.0625,   # and run 1/16" past the dimension line
    "dimgap": 0.0625,   # text 1/16" above the line
}


def add_dimstyle(doc: Drawing, plot_scale: float) -> None:
    """The FF dimension style (SPEC-43, 43.1): fractional inches to 1/16", ticks, text above the line, in
    FF_TEXT. The inch mark comes with the designer's text; ezdxf doesn't write DIMPOST, so a dimension
    CAD re-measures has none."""
    style = doc.dimstyles.new(DIMSTYLE)
    for key, value in DIMSTYLE_PAPER.items():
        style.dxf.set(key, value)
    style.dxf.dimscale = plot_scale
    style.dxf.dimtxsty = TEXT_STYLE
    style.dxf.dimtad = 1        # text above the dimension line
    style.dxf.dimtih = 0        # text aligned with the line, inside
    style.dxf.dimtoh = 0        # and outside
    style.dxf.dimlunit = 5      # fractional
    style.dxf.dimdec = 4        # to 1/16"
    style.dxf.dimfrac = 2       # not stacked: 30 1/2
    style.dxf.dimdsep = ord(".")


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
    stream = io.StringIO()
    doc.write(stream)
    return doc.encode(stream.getvalue())
