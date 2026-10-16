"""Swing-mark payload, visibility, layer style and PDF anchors (SPEC-HP2 step c)."""

import base64
import copy
import io
import json
from zipfile import ZipFile

import ezdxf
import pytest
from ezdxf.addons.drawing import Frontend
from pydantic import ValidationError
from pypdf import PdfReader
from pypdf.generic import ContentStream

from src.drawing.bundle import draw
from src.drawing.elevation_dxf import build_elevation_dxf, make_elevation_doc
from src.drawing.models import DrawingPayload


DOOR = {
    "id": "door", "kind": "face", "x": 1, "z": 4, "width": 16, "height": 24,
    "back": 24, "front": 25, "coversBoxEdges": True,
}
SHADE = {
    "id": "shade", "kind": "panel", "x": 1, "z": 16, "width": 16, "height": 12,
    "back": 25, "front": 26, "coversBoxEdges": False,
}
MARK = {"partId": "door", "lines": [
    {"x1": 1, "z1": 16, "x2": 17, "z2": 28},
    {"x1": 1, "z1": 16, "x2": 17, "z2": 4},
]}
EXPECTED = [((1, 16), (17, 28)), ((1, 16), (17, 4))]


def _payload(parts=None, marks=None):
    return copy.deepcopy({
        "payloadVersion": 1, "units": "in", "room": {"id": "room", "name": "Room"},
        "elevations": [{
            "key": "wall:front", "letter": "A", "wallId": "wall", "side": "front",
            "title": "Elevation A", "wallLabel": "Wall A", "length": 48, "height": 96,
            "parts": parts if parts is not None else [DOOR],
            "swingMarks": marks if marks is not None else [MARK],
        }],
    })


def _doc(payload):
    model = DrawingPayload.model_validate(payload)
    return make_elevation_doc(model.elevations[0], model.room)


def _segments(doc, layer):
    return [(tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2])
            for line in doc.modelspace().query(f'LINE[layer=="{layer}"]')]


def test_two_swing_segments_use_the_finest_dashed_black_layer():
    doc = _doc(_payload())
    assert _segments(doc, "SWING_MARKS") == EXPECTED
    layer = doc.layers.get("SWING_MARKS")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (7, "DASHED", 9)
    assert doc.header["$LTSCALE"] == 12
    assert _segments(doc, "HIDDEN") == []
    assert len(_segments(doc, "FACES")) == 4
    # Marks add no face boundaries and don't occlude the parts behind their face.
    behind = {**DOOR, "id": "behind", "kind": "cabinet", "front": 23, "back": 22}
    transparent = {**DOOR, "opaque": False}
    with_marks = _doc(_payload([transparent, behind]))
    without_marks = _doc(_payload([transparent, behind], []))
    for layer in ("FACES", "CABINETS", "HIDDEN"):
        assert _segments(with_marks, layer) == _segments(without_marks, layer)


def test_nearer_top_half_drops_the_upper_mark_without_hidden_mark_segments():
    doc = _doc(_payload([DOOR, SHADE]))
    assert _segments(doc, "SWING_MARKS") == [EXPECTED[1]]
    # Only the face's outline contributes hidden lines, never its swing marks.
    assert _segments(doc, "HIDDEN") == _segments(_doc(_payload([DOOR, SHADE], [])), "HIDDEN")
    assert all(start[0] == end[0] or start[1] == end[1]
               for start, end in _segments(doc, "HIDDEN"))


def test_partly_covered_marks_clip_at_the_nearer_part_depth():
    shade = {**SHADE, "z": 22, "height": 6}
    doc = _doc(_payload([DOOR, shade]))
    assert _segments(doc, "SWING_MARKS") == [((1, 16), (9, 22)), EXPECTED[1]]
    # A non-opaque or equally deep part must not hide either segment.
    for change in ({"opaque": False}, {"front": DOOR["front"]}):
        assert _segments(_doc(_payload([DOOR, {**shade, **change}])), "SWING_MARKS") == EXPECTED


def test_swing_marks_validate_part_ids_nonempty_lines_and_unknown_keys():
    with pytest.raises(ValidationError, match="Swing marks name unknown part ids: nope"):
        DrawingPayload.model_validate(_payload(marks=[{**MARK, "partId": "nope"}]))
    for mark in (
        {**MARK, "partId": ""},
        {**MARK, "lines": []},
        {"partId": "door"},
        {**MARK, "color": "red"},
        {**MARK, "lines": [{**MARK["lines"][0], "color": "red"}]},
    ):
        with pytest.raises(ValidationError):
            DrawingPayload.model_validate(_payload(marks=[mark]))


def test_omitted_swing_marks_default_to_empty_and_preserve_dxf(monkeypatch):
    monkeypatch.setattr(ezdxf.options, "write_fixed_meta_data_for_testing", True)
    payload = _payload(marks=[])
    del payload["elevations"][0]["swingMarks"]
    model = DrawingPayload.model_validate(payload)
    assert model.elevations[0].swingMarks == []
    assert json.loads(model.model_dump_json(exclude_defaults=True)) == payload
    explicit = DrawingPayload.model_validate(_payload(marks=[]))
    assert build_elevation_dxf(model.elevations[0], model.room) == build_elevation_dxf(
        explicit.elevations[0], explicit.room,
    )
    doc = _doc(payload)
    assert _segments(doc, "SWING_MARKS") == []
    assert _segments(doc, "FACES") == [
        ((1, 4), (17, 4)), ((17, 4), (17, 28)),
        ((17, 28), (1, 28)), ((1, 28), (1, 4)),
    ]
    assert _segments(doc, "HIDDEN") == []


def test_bundle_pdf_frontend_draws_both_swing_segments(monkeypatch):
    rendered = []
    original = Frontend.draw_line_entity

    def draw_line(frontend, entity, properties):
        if properties.layer == "SWING_MARKS":
            rendered.append((tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2]))
            assert properties.lineweight == pytest.approx(0.09)
        return original(frontend, entity, properties)

    monkeypatch.setattr(Frontend, "draw_line_entity", draw_line)
    payload = _payload()
    result = draw(payload)
    with ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as archive:
        assert json.loads(archive.read("payload.json")) == payload
        doc = ezdxf.read(io.StringIO(archive.read("elevation-A.dxf").decode("utf-8")))
        assert _segments(doc, "SWING_MARKS") == rendered == EXPECTED
        reader = PdfReader(io.BytesIO(archive.read("drawings.pdf")))
    assert len(reader.pages) == 1
    operations = ContentStream(reader.pages[0].get_contents(), reader).operations
    assert any(float(args[0]) == pytest.approx(0.09 * 72 / 25.4)
               for args, op in operations if op == b"w")
    assert any(op == b"S" for _, op in operations)
