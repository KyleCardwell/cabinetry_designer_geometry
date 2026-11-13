"""Elevation dimensions (SPEC-43): one DIMENSION per record the designer sends, on DIMENSIONS."""

from math import dist

from ezdxf.math import Vec2

from src.dxf.writer import DIMSTYLE
from src.projection.hlr import EPSILON

# 1/2" = 1'-0" when the payload doesn't say (SPEC-43).
DEFAULT_PLOT_SCALE = 24


def add_dimensions(modelspace, dimensions) -> None:
    """Horizontal or vertical linear dimensions in the FF style (SPEC-43.2). The block shows the designer's
    text, at `textX`/`textZ` when it's given; the entity keeps `<>` so CAD re-measures it if the drawing
    is edited.
    Each end's extension line from its own base, left out when it's on the line (SPEC-43.3).
    """
    for dimension in dimensions:
        if dimension.end - dimension.start <= EPSILON:
            continue
        start_base = dimension.base if dimension.startBase is None else dimension.startBase
        end_base = dimension.base if dimension.endBase is None else dimension.endBase
        if dimension.orientation == "vertical":
            base = (dimension.at, dimension.start)
            p1 = (start_base, dimension.start)
            p2 = (end_base, dimension.end)
            angle = 90
        else:
            base = (dimension.start, dimension.at)
            p1 = (dimension.start, start_base)
            p2 = (dimension.end, end_base)
            angle = 0
        override = modelspace.add_linear_dim(
            base=base,
            p1=p1,
            p2=p2,
            angle=angle,
            dimstyle=DIMSTYLE,
            text=dimension.text,
            override={
                "dimse1": 1 if abs(start_base - dimension.at) <= EPSILON else 0,
                "dimse2": 1 if abs(end_base - dimension.at) <= EPSILON else 0,
            },
            dxfattribs={"layer": "DIMENSIONS"},
        )
        if dimension.textX is not None and dimension.textZ is not None:
            # Text that doesn't fit, moved where the designer put it, with a leader (SPEC-DM7).
            override.set_location((dimension.textX, dimension.textZ), leader=False, relative=False)
            _add_leader(override, (dimension.textX, dimension.textZ))
        else:
            override.render()
        override.dimension.dxf.text = "<>"


def add_plan_dimensions(modelspace, dimensions) -> None:
    """Aligned dimensions in plan (SPEC-45), in the FF style. At offset 0 the dimension line is the
    measured line, with no extension lines."""
    for dimension in dimensions:
        if dist(dimension.start, dimension.end) <= EPSILON:
            continue
        on_line = 1 if abs(dimension.offset) <= EPSILON else 0
        override = modelspace.add_aligned_dim(
            p1=dimension.start,
            p2=dimension.end,
            distance=dimension.offset,
            dimstyle=DIMSTYLE,
            text=dimension.text,
            override={"dimse1": on_line, "dimse2": on_line},
            dxfattribs={"layer": "DIMENSIONS"},
        )
        if dimension.textAt is not None:
            override.set_location(dimension.textAt, leader=False, relative=False)
            _add_leader(override, dimension.textAt)
        else:
            override.render()
        override.dimension.dxf.text = "<>"


def _add_leader(override, text_at) -> None:
    """Render, then add one straight leader from the dimension line's midpoint to the moved text's near
    edge (half the text height plus the gap short of its centre), like the canvas. ezdxf's own leader
    bends to a corner of the text and underlines it, so it isn't used."""
    renderer = override.render()
    start = Vec2(renderer.dim_line_center)
    text = Vec2(text_at)
    measurement = renderer.measurement
    clear = measurement.text_height / 2 + measurement.text_gap
    if start.distance(text) <= clear:
        return
    end = text - (text - start).normalize(clear)
    block = override.dimension.doc.blocks.get(override.dimension.dxf.geometry)
    block.add_line(start, end, dxfattribs=renderer.dimension_line.dxfattribs())
