"""Elevation dimensions in the DXF (SPEC-43)."""

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
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())

# G1 elevation A's run overall row and its wall row, as the designer sends them (SPEC-43).
DIMENSIONS = [
    {"row": "lower.outer", "kind": "run", "start": 0, "end": 30, "base": 0, "at": -18, "text": '30"'},
    {"row": "lower.outer", "kind": "run", "start": 30, "end": 168, "base": 0, "at": -18, "text": '138"'},
    {"row": "openings", "kind": "gap", "start": 0, "end": 48, "base": 0, "at": -27, "text": '48"'},
    {"row": "openings", "kind": "opening", "start": 48, "end": 96, "base": 0, "at": -27, "text": '48"'},
    {"row": "upper.outer", "kind": "run", "start": 108.5, "end": 168, "base": 96, "at": 114, "text": '59 1/2"'},
]


def _payload(plot_scale=None):
    payload = copy.deepcopy(PAYLOAD)
    payload["elevations"][0]["dimensions"] = copy.deepcopy(DIMENSIONS)
    if plot_scale is not None:
        payload["plotScale"] = plot_scale
    return payload


def _dxf(payload, letter="A"):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read(f"elevation-{letter}.dxf").decode("utf-8")))


def _shown_text(doc, dimension):
    """The text the dimension's block shows."""
    return [entity.dxf.text for entity in doc.blocks.get(dimension.dxf.geometry) if entity.dxftype() == "MTEXT"]


def test_each_record_is_a_dimension_on_dimensions():
    doc = _dxf(_payload())
    dimensions = list(doc.modelspace().query("DIMENSION"))
    assert len(dimensions) == 5
    assert {dimension.dxf.layer for dimension in dimensions} == {"DIMENSIONS"}
    assert {dimension.dxf.dimstyle for dimension in dimensions} == {"FF"}
    first = dimensions[0]
    assert tuple(first.dxf.defpoint2)[:2] == (0, 0)
    assert tuple(first.dxf.defpoint3)[:2] == (30, 0)
    assert tuple(first.dxf.defpoint)[:2] == (0, -18)
    assert [dimension.get_measurement() for dimension in dimensions] == [30, 138, 48, 48, 59.5]
    above = dimensions[4]
    assert tuple(above.dxf.defpoint2)[:2] == (108.5, 96)
    assert tuple(above.dxf.defpoint)[:2] == (108.5, 114)


def test_the_block_shows_the_designers_text_and_cad_can_remeasure():
    doc = _dxf(_payload())
    dimensions = list(doc.modelspace().query("DIMENSION"))
    assert [_shown_text(doc, dimension) for dimension in dimensions] == [
        ['30"'], ['138"'], ['48"'], ['48"'], ['59 1/2"'],
    ]
    assert {dimension.dxf.text for dimension in dimensions} == {"<>"}


def test_the_style_is_paper_sizes_times_the_plot_scale():
    style = _dxf(_payload()).dimstyles.get("FF")
    assert style.dxf.dimscale == 24
    assert (style.dxf.dimtxt, style.dxf.dimtsz, style.dxf.dimexo, style.dxf.dimexe, style.dxf.dimgap) == (
        0.09375, 0.0625, 0.0625, 0.0625, 0.0625,
    )
    assert (style.dxf.dimlunit, style.dxf.dimdec, style.dxf.dimfrac, style.dxf.dimtad) == (5, 4, 2, 1)
    doc = _dxf(_payload(plot_scale=48))
    assert doc.dimstyles.get("FF").dxf.dimscale == 48
    dimension = next(iter(doc.modelspace().query("DIMENSION")))
    heights = [entity.dxf.char_height for entity in doc.blocks.get(dimension.dxf.geometry) if entity.dxftype() == "MTEXT"]
    assert heights == [4.5]


def test_the_title_moves_under_the_lowest_dimension_line():
    texts = {text.dxf.text: tuple(text.dxf.insert)[:2] for text in _dxf(_payload()).modelspace().query("TEXT")}
    assert texts == {"ELEVATION A": (0, -39), "Wall 1": (0, -45), "G1 Euro kitchen": (0, -50)}
    plain = {text.dxf.text: tuple(text.dxf.insert)[:2] for text in _dxf(_payload(), "B").modelspace().query("TEXT")}
    assert plain == {"ELEVATION B": (0, -12), "Wall 2": (0, -18), "G1 Euro kitchen": (0, -23)}
    assert list(_dxf(_payload(), "B").modelspace().query("DIMENSION")) == []


def test_payload_json_keeps_the_dimensions_and_the_plot_scale():
    payload = _payload(plot_scale=24)
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    assert json.loads(archive.read("payload.json")) == payload


def test_rejects_a_bad_plot_scale_or_an_unknown_dimension_field():
    with pytest.raises(ValidationError):
        draw(_payload(plot_scale=0))
    payload = _payload()
    payload["elevations"][0]["dimensions"][0]["offset"] = 9
    with pytest.raises(ValidationError):
        draw(payload)



def test_text_that_doesnt_fit_goes_where_the_designer_put_it():
    payload = _payload()
    payload["elevations"][0]["dimensions"] = [
        {"row": "lower.inner", "kind": "piece", "start": 0, "end": 0.75, "base": 0, "at": -9,
         "text": '3/4"', "textX": 0.375, "textZ": -12.375},
        {"row": "lower.inner", "kind": "piece", "start": 0.75, "end": 29.25, "base": 0, "at": -9, "text": '28 1/2"'},
    ]
    doc = _dxf(payload)
    moved, inline = list(doc.modelspace().query("DIMENSION"))
    assert tuple(moved.dxf.text_midpoint)[:2] == (0.375, -12.375)
    assert moved.dxf.dimtype & 128 == 128
    texts = [entity for entity in doc.blocks.get(moved.dxf.geometry) if entity.dxftype() == "MTEXT"]
    assert [(text.dxf.text, tuple(text.dxf.insert)[:2]) for text in texts] == [('3/4"', (0.375, -12.375))]
    assert [entity.dxftype() for entity in doc.blocks.get(moved.dxf.geometry)].count("LINE") == 3
    assert inline.dxf.dimtype & 128 == 0
    assert json.loads(zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"]))).read("payload.json")) == payload


# G1 elevation A's left edge, as the designer sends it (SPEC-43.2): toe kick (its text moved), box, molding, wall.
VERTICAL = [
    {"row": "left.inner", "orientation": "vertical", "kind": "toe-kick", "start": 0, "end": 4, "base": 0, "at": -9,
     "text": '4"', "textX": -15.375, "textZ": 2},
    {"row": "left.inner", "orientation": "vertical", "kind": "box", "start": 4, "end": 90, "base": 0, "at": -9,
     "text": '86"'},
    {"row": "left.inner", "orientation": "vertical", "kind": "molding", "start": 90, "end": 96, "base": 0, "at": -9,
     "text": '6"'},
    {"row": "left.outer", "orientation": "vertical", "kind": "wall", "start": 0, "end": 96, "base": 0, "at": -21.75,
     "text": '96"'},
]


def test_a_vertical_record_dimensions_up_the_wall():
    payload = _payload()
    payload["elevations"][0]["dimensions"] = copy.deepcopy(VERTICAL)
    doc = _dxf(payload)
    toe, box, molding, wall = doc.modelspace().query("DIMENSION")
    assert {dimension.dxf.angle for dimension in (toe, box, molding, wall)} == {90}
    assert tuple(box.dxf.defpoint2)[:2] == (0, 4)
    assert tuple(box.dxf.defpoint3)[:2] == (0, 90)
    assert tuple(box.dxf.defpoint)[:2] == (-9, 4)
    assert [dimension.get_measurement() for dimension in (toe, box, molding, wall)] == [4, 86, 6, 96]
    assert tuple(wall.dxf.defpoint)[:2] == (-21.75, 0)
    assert tuple(toe.dxf.text_midpoint)[:2] == (-15.375, 2)
    assert toe.dxf.dimtype & 128 == 128
    texts = [entity for entity in doc.blocks.get(box.dxf.geometry) if entity.dxftype() == "MTEXT"]
    assert [(text.dxf.text, text.dxf.rotation) for text in texts] == [('86"', 90)]


def test_vertical_dimensions_dont_move_the_title_and_round_trip():
    payload = _payload()
    payload["elevations"][0]["dimensions"] = copy.deepcopy(VERTICAL)
    texts = {text.dxf.text: tuple(text.dxf.insert)[:2] for text in _dxf(payload).modelspace().query("TEXT")}
    assert texts == {"ELEVATION A": (0, -12), "Wall 1": (0, -18), "G1 Euro kitchen": (0, -23)}
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    assert json.loads(archive.read("payload.json")) == payload
    payload["elevations"][0]["dimensions"][0]["orientation"] = "diagonal"
    with pytest.raises(ValidationError):
        draw(payload)
