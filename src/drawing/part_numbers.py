"""Draw the designer's pre-positioned boxed part numbers and leaders (GC5)."""

from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from src.dxf.writer import TEXT_STYLE

from .models import PayloadPartNumber


def add_part_numbers(modelspace: Modelspace, badges: list[PayloadPartNumber]) -> None:
    """Fill and outline each badge, then centre its text and draw its leader."""
    for badge in badges:
        attrs = {"layer": "PART_NUMBERS"}
        x0, x1 = badge.x - badge.width / 2, badge.x + badge.width / 2
        z0, z1 = badge.z - badge.height / 2, badge.z + badge.height / 2
        corners = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
        hatch = modelspace.add_hatch(dxfattribs=attrs)
        hatch.set_solid_fill(color=7, style=0, rgb=(255, 255, 255))
        hatch.paths.add_polyline_path(corners, is_closed=True)
        modelspace.add_lwpolyline(corners, close=True, dxfattribs=attrs)
        modelspace.add_text(
            badge.text,
            height=2 * badge.height / 3,
            dxfattribs={**attrs, "style": TEXT_STYLE},
        ).set_placement((badge.x, badge.z), align=TextEntityAlignment.MIDDLE_CENTER)
        if badge.leader is not None:
            leader = badge.leader
            modelspace.add_line(
                (leader.x1, leader.z1), (leader.x2, leader.z2), dxfattribs=attrs,
            )
