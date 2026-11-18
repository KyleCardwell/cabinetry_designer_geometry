"""Elevation markers and labels in plan (SPEC-45.1)."""

import base64
import copy
import io
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest
from pydantic import ValidationError

from src.drawing.bundle import draw
from src.drawing.models import PayloadPlanMark
from src.drawing.plan_marks import add_plan_marks, mark_points

ROOT = Path(__file__).resolve().parent.parent
ELEVATIONS = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())

PLAN = {
    "parts": [{"id": "A:wall", "kind": "wall", "points": [[0, 0], [120, 0], [120, -4.5], [0, -4.5]]}],
    "marks": [
        # Looking at wall A from the room: the flag points down, at the wall.
        {"kind": "elevation", "at": [60, 40], "text": "A", "direction": [0, -1]},
        {"kind": "label", "at": [60, -7.5], "text": "W1 · 48\""},
        {"kind": "label", "at": [-7.5, 30], "text": "D1 · 30\"", "rotation": 90},
    ],
}
PAYLOAD = {**ELEVATIONS, "plan": PLAN}


def _modelspace(payload):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read("plan.dxf").decode("utf-8"))).modelspace()


def _round(point):
    return tuple(round(value, 4) + 0 for value in tuple(point)[:2])


def test_an_elevation_marker_has_a_wide_triangle_behind_a_white_circle_and_letter_GC5_1():
    msp = ezdxf.new().modelspace()
    mark = PayloadPlanMark(kind="elevation", at=(0, 0), direction=(0, 1), text="A")
    add_plan_marks(msp, [mark], 24)
    assert [entity.dxftype() for entity in msp] == ["LWPOLYLINE", "HATCH", "HATCH", "CIRCLE", "TEXT"]
    triangle, fill, circle_fill, circle, letter = list(msp)
    assert all(entity.dxf.layer == "MARKERS" for entity in (triangle, fill, circle_fill, circle))
    assert triangle.closed
    assert [_round(point) for point in triangle.get_points("xy")] == [(-9, 0), (0, 10.8), (9, 0)]
    assert (fill.dxf.solid_fill, fill.dxf.color) == (1, 256)
    [triangle_path] = fill.paths
    assert triangle_path.is_closed
    assert [_round(point) for point in triangle_path.vertices] == [(-9, 0), (0, 10.8), (9, 0)]
    assert (circle_fill.dxf.solid_fill, circle_fill.dxf.color, circle_fill.dxf.hatch_style) == (1, 7, 0)
    assert circle_fill.rgb == (255, 255, 255)
    [circle_path] = circle_fill.paths
    [arc] = circle_path.edges
    assert arc.EDGE_TYPE == "ArcEdge"
    assert (_round(arc.center), arc.radius, arc.start_angle, arc.end_angle, arc.ccw) == ((0, 0), 6, 0, 360, True)
    assert (_round(circle.dxf.center), circle.dxf.radius) == ((0, 0), 6)
    assert (letter.dxf.layer, letter.dxf.style, letter.dxf.text, _round(letter.dxf.align_point)) == (
        "TEXT", "FF_TEXT", "A", (0, 0),
    )
    assert letter.dxf.height == pytest.approx(4.8)
    assert (letter.dxf.halign, letter.dxf.valign) == (1, 2)


def test_marker_points_reach_the_triangle_tip_GC5_1():
    mark = PayloadPlanMark(kind="elevation", at=(0, 0), direction=(0, 1), text="A")
    assert mark_points([mark], 24) == [(0, -10.8), (0, 10.8)]


def test_a_label_is_centred_text_at_dimension_size_turned_as_sent():
    labels = [
        (text.dxf.text, _round(text.dxf.align_point), text.dxf.height, text.dxf.rotation, text.dxf.halign, text.dxf.valign)
        for text in _modelspace(PAYLOAD).query('TEXT[layer=="TEXT"]')
        if "·" in text.dxf.text
    ]
    assert labels == [
        ('W1 · 48"', (60, -7.5), 2.25, 0, 1, 2),
        ('D1 · 30"', (-7.5, 30), 2.25, 90, 1, 2),
    ]


def test_rejects_an_unknown_mark_kind_or_no_text():
    for change in ({"kind": "number"}, {"text": ""}):
        payload = copy.deepcopy(PAYLOAD)
        payload["plan"]["marks"][0].update(change)
        with pytest.raises(ValidationError):
            draw(payload)
