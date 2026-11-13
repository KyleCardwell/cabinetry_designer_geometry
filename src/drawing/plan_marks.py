"""Elevation markers and labels in plan (SPEC-45.1). The designer places them; geometry draws them."""

from ezdxf.enums import TextEntityAlignment

from src.dxf.writer import DIMSTYLE_PAPER, TEXT_STYLE

# Paper inches (SPEC-45.1); the designer's planMarks uses the same numbers to place markers.
MARKER_RADIUS = 0.25
MARKER_FLAG = 0.1875
MARKER_TEXT = 0.125


def mark_points(marks, plot_scale) -> list:
    """The lowest and highest points each mark reaches, for the title."""
    points = []
    for mark in marks:
        reach = MARKER_RADIUS * plot_scale if mark.kind == "elevation" else 0
        points += [(mark.at[0], mark.at[1] - reach), (mark.at[0], mark.at[1] + reach)]
    return points


def add_plan_marks(modelspace, marks, plot_scale) -> None:
    radius = MARKER_RADIUS * plot_scale
    flag = MARKER_FLAG * plot_scale
    for mark in marks:
        x, y = mark.at
        if mark.kind == "elevation":
            modelspace.add_circle((x, y), radius, dxfattribs={"layer": "MARKERS"})
            dx, dy = mark.direction or (0, 1)
            half = radius * 0.6
            base = (x + dx * radius, y + dy * radius)
            triangle = [
                (base[0] - dy * half, base[1] + dx * half),
                (x + dx * (radius + flag), y + dy * (radius + flag)),
                (base[0] + dy * half, base[1] - dx * half),
            ]
            modelspace.add_lwpolyline(triangle, close=True, dxfattribs={"layer": "MARKERS"})
            hatch = modelspace.add_hatch(dxfattribs={"layer": "MARKERS"})
            hatch.set_solid_fill(color=256)
            hatch.paths.add_polyline_path(triangle, is_closed=True)
            height, rotation = MARKER_TEXT * plot_scale, 0
        else:
            height, rotation = DIMSTYLE_PAPER["dimtxt"] * plot_scale, mark.rotation
        modelspace.add_text(
            mark.text,
            height=height,
            rotation=rotation,
            dxfattribs={"layer": "TEXT", "style": TEXT_STYLE},
        ).set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)
