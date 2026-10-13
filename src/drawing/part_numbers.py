"""Draw the designer's pre-positioned part number badges (SPEC-50.13)."""

from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from src.dxf.writer import TEXT_STYLE

from .models import PayloadPartNumber


def add_part_numbers(modelspace: Modelspace, badges: list[PayloadPartNumber]) -> None:
    """Outline each slot, centre its text, and draw its optional leader."""
    for badge in badges:
        radius = badge.height / 2
        attrs = {"layer": "PART_NUMBERS"}
        if badge.width == badge.height:
            modelspace.add_circle((badge.x, badge.z), radius, dxfattribs=attrs)
        else:
            half_flat = (badge.width - badge.height) / 2
            left, right = badge.x - half_flat, badge.x + half_flat
            bottom, top = badge.z - radius, badge.z + radius
            modelspace.add_lwpolyline(
                [(left, bottom, 0), (right, bottom, 1),
                 (right, top, 0), (left, top, 1)],
                format="xyb", close=True, dxfattribs=attrs,
            )
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
