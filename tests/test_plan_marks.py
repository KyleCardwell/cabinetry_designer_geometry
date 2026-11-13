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


def test_an_elevation_marker_is_a_circle_a_filled_flag_and_its_letter_at_paper_size():
    msp = _modelspace(PAYLOAD)
    [circle] = msp.query("CIRCLE")
    assert (circle.dxf.layer, _round(circle.dxf.center), circle.dxf.radius) == ("MARKERS", (60, 40), 6)
    [flag] = msp.query('LWPOLYLINE[layer=="MARKERS"]')
    assert flag.closed
    assert [_round(point) for point in flag.get_points("xy")] == [(63.6, 34), (60, 29.5), (56.4, 34)]
    [fill] = msp.query('HATCH[layer=="MARKERS"]')
    assert (fill.dxf.solid_fill, fill.dxf.color) == (1, 256)
    letter = [text for text in msp.query("TEXT") if text.dxf.text == "A"][0]
    assert (letter.dxf.layer, letter.dxf.style, letter.dxf.height, _round(letter.dxf.align_point)) == (
        "TEXT", "FF_TEXT", 3, (60, 40),
    )
    payload = copy.deepcopy(PAYLOAD)
    payload["plotScale"] = 48
    assert next(iter(_modelspace(payload).query("CIRCLE"))).dxf.radius == 12


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
