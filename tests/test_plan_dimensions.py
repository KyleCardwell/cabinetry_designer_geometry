"""Plan dimensions (SPEC-45)."""

import base64
import copy
import io
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest
from ezdxf.entities import DimStyleOverride
from pydantic import ValidationError

from src.drawing.bundle import draw

ROOT = Path(__file__).resolve().parent.parent
ELEVATIONS = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())

# A 120" wall along x with a 4 1/2" thickness below it, a 60" wall going down from its right end.
PLAN = {
    "parts": [
        {"id": "A:wall", "kind": "wall", "points": [[0, 0], [120, 0], [124.5, -4.5], [0, -4.5]]},
        {"id": "B:wall", "kind": "wall", "points": [[120, 0], [120, -60], [124.5, -60], [124.5, -4.5]]},
    ],
    "dimensions": [
        # Wall A's length, 9" below its back face: to the right of start→end.
        {"row": "wall", "kind": "wall", "start": [0, -4.5], "end": [120, -4.5], "offset": -9, "text": '120"'},
        # Wall B's length, read from the right: start at the bottom, 9" past its back face.
        {"row": "wall", "kind": "wall", "start": [124.5, -60], "end": [124.5, 0], "offset": -9, "text": '60"'},
        # On its own line, no extension lines; the text moved off it.
        {"row": "depth", "kind": "depth", "start": [30, -24], "end": [30, 0], "offset": 0, "text": '24"',
         "textAt": [36, -12]},
    ],
}
PAYLOAD = {**ELEVATIONS, "plan": PLAN}


def _dxf(payload):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read("plan.dxf").decode("utf-8")))


def _round(point):
    return tuple(round(value, 4) + 0 for value in tuple(point)[:2])


def test_each_record_is_an_aligned_dimension_on_dimensions():
    doc = _dxf(PAYLOAD)
    dimensions = list(doc.modelspace().query("DIMENSION"))
    # Aligned: a linear dimension at the angle of start→end.
    assert [(d.dxf.layer, d.dxf.dimstyle, d.dxf.angle) for d in dimensions] == [
        ("DIMENSIONS", "FF", 0), ("DIMENSIONS", "FF", 90), ("DIMENSIONS", "FF", 90),
    ]
    assert [d.get_measurement() for d in dimensions] == pytest.approx([120, 60, 24])
    assert [(_round(d.dxf.defpoint2), _round(d.dxf.defpoint3), _round(d.dxf.defpoint)) for d in dimensions] == [
        ((0, -4.5), (120, -4.5), (0, -13.5)),
        ((124.5, -60), (124.5, 0), (133.5, -60)),
        ((30, -24), (30, 0), (30, -24)),
    ]
    assert {d.dxf.text for d in dimensions} == {"<>"}
    shown = [[e.dxf.text for e in doc.blocks.get(d.dxf.geometry) if e.dxftype() == "MTEXT"] for d in dimensions]
    assert shown == [['120"'], ['60"'], ['24"']]
    assert doc.dimstyles.get("FF").dxf.dimscale == 24


def test_on_the_line_no_extension_lines_and_moved_text_where_sent():
    doc = _dxf(PAYLOAD)
    dimensions = list(doc.modelspace().query("DIMENSION"))
    flags = [(DimStyleOverride(d).get("dimse1"), DimStyleOverride(d).get("dimse2")) for d in dimensions]
    assert flags == [(0, 0), (0, 0), (1, 1)]
    moved = [e for e in doc.blocks.get(dimensions[2].dxf.geometry) if e.dxftype() == "MTEXT"][0]
    assert _round(moved.dxf.insert) == (36, -12)


def test_the_title_goes_under_the_lowest_dimension_and_a_plan_without_them_is_unchanged():
    texts = [(t.dxf.text, _round(t.dxf.insert)) for t in _dxf(PAYLOAD).modelspace().query("TEXT")]
    assert texts == [("PLAN", (0, -72)), ("G1 Euro kitchen", (0, -78))]
    low = copy.deepcopy(PAYLOAD)
    low["plan"]["dimensions"][1]["start"] = [124.5, -70]
    texts = [(t.dxf.text, _round(t.dxf.insert)) for t in _dxf(low).modelspace().query("TEXT")]
    assert texts == [("PLAN", (0, -82)), ("G1 Euro kitchen", (0, -88))]
    bare = copy.deepcopy(PAYLOAD)
    del bare["plan"]["dimensions"]
    assert not list(_dxf(bare).modelspace().query("DIMENSION"))


def test_rejects_a_dimension_with_no_text_or_a_three_number_point():
    for change in ({"text": ""}, {"start": [0, 0, 0]}):
        payload = copy.deepcopy(PAYLOAD)
        payload["plan"]["dimensions"][0].update(change)
        with pytest.raises(ValidationError):
            draw(payload)
