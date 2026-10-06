"""Elevation dimensions (SPEC-43): one DIMENSION per record the designer sends, on DIMENSIONS."""

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
            # Text that doesn't fit, moved where the designer put it (SPEC-43.1), with no leader.
            override.set_location((dimension.textX, dimension.textZ), leader=False, relative=False)
        override.render()
        override.dimension.dxf.text = "<>"
