"""Elevation dimensions (SPEC-43): one DIMENSION per record the designer sends, on DIMENSIONS."""

from src.dxf.writer import DIMSTYLE
from src.projection.hlr import EPSILON

# 1/2" = 1'-0" when the payload doesn't say (SPEC-43).
DEFAULT_PLOT_SCALE = 24


def add_dimensions(modelspace, dimensions) -> None:
    """Horizontal linear dimensions in the FF style. The block shows the designer's text; the entity keeps
    `<>` so CAD re-measures it if the drawing is edited."""
    for dimension in dimensions:
        if dimension.end - dimension.start <= EPSILON:
            continue
        override = modelspace.add_linear_dim(
            base=(dimension.start, dimension.at),
            p1=(dimension.start, dimension.base),
            p2=(dimension.end, dimension.base),
            dimstyle=DIMSTYLE,
            text=dimension.text,
            dxfattribs={"layer": "DIMENSIONS"},
        )
        override.render()
        override.dimension.dxf.text = "<>"
