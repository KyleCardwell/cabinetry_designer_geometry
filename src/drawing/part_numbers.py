"""Draw the designer's pre-positioned part number text and leaders (SPEC-50.14)."""

from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from src.dxf.writer import TEXT_STYLE

from .models import PayloadPartNumber


def add_part_numbers(modelspace: Modelspace, badges: list[PayloadPartNumber]) -> None:
    """Centre each badge's text and draw its optional leader."""
    for badge in badges:
        attrs = {"layer": "PART_NUMBERS"}
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
