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
    assert (style.dxf.dimlunit, style.dxf.dimdec, style.dxf.dimfrac, style.dxf.dimtad, style.dxf.dimtix) == (5, 4, 2, 0, 1)
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
    assert moved.dxf.dimtype & 128 == 128
    texts = [entity for entity in doc.blocks.get(moved.dxf.geometry) if entity.dxftype() == "MTEXT"]
    assert [(text.dxf.text, tuple(text.dxf.insert)[:2]) for text in texts] == [('3/4"', (0.375, -12.375))]
    _assert_leader(doc, moved, (0.375, -9), (0.375, -12.375))
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
    # With a leader, ezdxf stores its bend in text_midpoint; MTEXT holds the label centre.
    toe_text, = doc.blocks.get(toe.dxf.geometry).query("MTEXT")
    assert tuple(toe_text.dxf.insert)[:2] == (-15.375, 2)
    assert toe.dxf.dimtype & 128 == 128
    _assert_leader(doc, toe, (-9, 2), (-15.375, 2))
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


# G1 elevation A's casing clearance to the tall, and a pin callout from the window's centre to the sink's
# centre 3" right of it, as the designer sends them (SPEC-43.3).
CALLOUTS = [
    {"row": "clearances", "kind": "clearance", "start": 30, "end": 45, "base": 64.5, "at": 64.5, "text": '15"'},
    {"row": "pins", "kind": "pin", "start": 72, "end": 75, "base": 48, "startBase": 66, "endBase": 34.5, "at": 48,
     "text": 'CL 3"', "textX": 73.5, "textZ": 54.375},
    {"row": "pins", "kind": "pin", "start": 0, "end": 60, "base": 40, "startBase": 40, "endBase": 34.5, "at": 40,
     "text": '60"'},
]


def _lines(doc, dimension):
    return sorted(
        (tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2])
        for entity in doc.blocks.get(dimension.dxf.geometry) if entity.dxftype() == "LINE"
    )


def _assert_split_line(doc, dimension, axis, at, start, end):
    lines = [
        (p1[axis], p2[axis]) for p1, p2 in _lines(doc, dimension)
        if p1[1 - axis] == pytest.approx(at) and p2[1 - axis] == pytest.approx(at)
    ]
    assert len(lines) == 2
    assert lines[0][0] == pytest.approx(start)
    assert lines[1][1] == pytest.approx(end)
    assert start < lines[0][1] < (start + end) / 2 < lines[1][0] < end
    assert lines[0][1] + lines[1][0] == pytest.approx(start + end)


def _assert_leader(doc, dimension, midpoint, text_at):
    """One straight leader from the midpoint toward the text, stopping short of it; nothing under the text."""
    leaders = [
        (p1, p2) for p1, p2 in _lines(doc, dimension)
        if p1 == pytest.approx(midpoint) or p2 == pytest.approx(midpoint)
    ]
    leaders = [
        (p1, p2) if p1 == pytest.approx(midpoint) else (p2, p1) for p1, p2 in leaders
        if sum((q[i] - midpoint[i]) * (text_at[i] - midpoint[i]) for q in (p1, p2) for i in (0, 1)) > 0
    ]
    assert len(leaders) == 1
    (_, end), = leaders
    reach = sum((end[i] - midpoint[i]) ** 2 for i in (0, 1)) ** 0.5
    full = sum((text_at[i] - midpoint[i]) ** 2 for i in (0, 1)) ** 0.5
    assert 0 < reach < full
    # straight at the text: the end is on the midpoint→text line
    cross = (end[0] - midpoint[0]) * (text_at[1] - midpoint[1]) - (end[1] - midpoint[1]) * (text_at[0] - midpoint[0])
    assert cross == pytest.approx(0, abs=1e-9)
    # no ezdxf underline: no line runs along the text's near edge
    assert not any(p1 != pytest.approx(midpoint) and p2 != pytest.approx(midpoint) and (
        p1 == pytest.approx(end) or p2 == pytest.approx(end)) for p1, p2 in _lines(doc, dimension))


@pytest.mark.parametrize("orientation, axis, text_at", [
    ("horizontal", 0, (15, -10)),
    ("vertical", 1, (-10, 15)),
])
def test_inline_text_is_centred_in_a_split_dimension_line(orientation, axis, text_at):
    payload = _payload(plot_scale=24)
    payload["elevations"][0]["dimensions"] = [
        {"row": "outer", "kind": "run", "orientation": orientation,
         "start": 0, "end": 30, "base": 0, "at": -10, "text": '30"'},
    ]
    doc = _dxf(payload)
    dimension, = doc.modelspace().query("DIMENSION")
    _assert_split_line(doc, dimension, axis, -10, 0, 30)
    text, = doc.blocks.get(dimension.dxf.geometry).query("MTEXT")
    assert tuple(text.dxf.insert)[:2] == pytest.approx(text_at)
    assert text.dxf.attachment_point == 5  # middle centre
    assert text.dxf.rotation == pytest.approx(90 * axis)


def test_an_extension_line_on_its_dimension_line_is_left_out():
    payload = _payload()
    payload["elevations"][0]["dimensions"] = copy.deepcopy(CALLOUTS)
    doc = _dxf(payload)
    clearance, pin, wall_pin = doc.modelspace().query("DIMENSION")
    assert [dimension.get_measurement() for dimension in (clearance, pin, wall_pin)] == [15, 3, 60]
    assert tuple(clearance.dxf.defpoint2)[:2] == (30, 64.5)
    _assert_split_line(doc, clearance, 0, 64.5, 30, 45)
    assert len(_lines(doc, clearance)) == 2
    _assert_split_line(doc, wall_pin, 0, 40, 0, 60)
    assert len(_lines(doc, wall_pin)) == 3
    assert ((60, 36), (60, 41.5)) in _lines(doc, wall_pin)


def test_each_end_of_a_dimension_can_have_its_own_base_and_round_trips():
    payload = _payload()
    payload["elevations"][0]["dimensions"] = copy.deepcopy(CALLOUTS)
    doc = _dxf(payload)
    pin = list(doc.modelspace().query("DIMENSION"))[1]
    assert tuple(pin.dxf.defpoint2)[:2] == (72, 66)
    assert tuple(pin.dxf.defpoint3)[:2] == (75, 34.5)
    assert tuple(pin.dxf.defpoint)[:2] == (72, 48)
    assert len(_lines(doc, pin)) == 4  # lines, extension lines, one straight leader
    assert all(line in _lines(doc, pin) for line in [
        ((72, 48), (75, 48)), ((72, 64.5), (72, 46.5)), ((75, 36), (75, 49.5)),
    ])
    _assert_leader(doc, pin, (73.5, 48), (73.5, 54.375))
    pin_text, = doc.blocks.get(pin.dxf.geometry).query("MTEXT")
    assert tuple(pin_text.dxf.insert)[:2] == (73.5, 54.375)
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    assert json.loads(archive.read("payload.json")) == payload
