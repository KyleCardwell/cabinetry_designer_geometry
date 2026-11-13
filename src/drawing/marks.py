"""Centreline marks (SPEC-43.3). The designer places them; geometry draws them."""

from ezdxf.enums import TextEntityAlignment

from src.dxf.writer import DIMSTYLE_PAPER, TEXT_STYLE


def add_marks(modelspace, marks, plot_scale) -> None:
    for mark in marks:
        modelspace.add_line(
            (mark.x, mark.bottom), (mark.x, mark.top),
            dxfattribs={"layer": "CENTERLINES"},
        )
        modelspace.add_text(
            mark.text,
            height=DIMSTYLE_PAPER["dimtxt"] * plot_scale,
            dxfattribs={"layer": "DIMENSIONS", "style": TEXT_STYLE},
        ).set_placement(
            (mark.textX, mark.textZ), align=TextEntityAlignment.MIDDLE_CENTER,
        )
