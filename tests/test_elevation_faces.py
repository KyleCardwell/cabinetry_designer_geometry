"""Combined elevation face outlines and supplied depth notes (SPEC-CE step b)."""

import copy

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from pydantic import ValidationError

from src.drawing.elevation_dxf import build_elevation_dxf, make_elevation_doc
from src.drawing.models import PayloadElevation, PayloadRoom


ROOM = PayloadRoom(id="room", name="Combined walls")
ELEVATION = {
    "key": "combined", "letter": "A", "wallId": "C", "side": "front",
    "title": "Elevation A", "wallLabel": "C / B / A", "length": 240, "height": 96,
}
FACES = [
    {"key": "C", "wallId": "C", "side": "front", "wallLabel": "C",
     "dx": 0, "depth": 0, "length": 80, "height": 96},
    {"key": "B:back", "wallId": "B", "side": "back", "wallLabel": "B",
     "dx": 80, "depth": -16, "length": 60, "height": 96, "note": '16" back'},
    {"key": "A", "wallId": "A", "side": "front", "wallLabel": "A",
     "dx": 140, "depth": 0, "length": 100, "height": 96, "note": None},
]


def _rectangles(modelspace):
    rectangles = list(modelspace.query('LWPOLYLINE[layer=="WALLS"]'))
    assert all(rectangle.closed for rectangle in rectangles)
    return [list(rectangle.get_points("xy")) for rectangle in rectangles]


def test_combined_face_rectangles_and_centred_note():
    for scale, middle_height in ((24, 96), (48, 72)):
        faces = copy.deepcopy(FACES)
        faces[1]["height"] = middle_height
        elevation = PayloadElevation.model_validate({**ELEVATION, "faces": faces})
        assert elevation.model_dump(exclude_defaults=True)["faces"] == [
            {key: value for key, value in face.items() if value is not None} for face in faces
        ]
        msp = make_elevation_doc(elevation, ROOM, scale).modelspace()
        assert _rectangles(msp) == [
            [(0, 0), (80, 0), (80, 96), (0, 96)],
            [(80, 0), (140, 0), (140, middle_height), (80, middle_height)],
            [(140, 0), (240, 0), (240, 96), (140, 96)],
        ]
        notes = list(msp.query('TEXT[layer=="DIMENSIONS"]'))
        assert len(notes) == 1
        note = notes[0]
        alignment, position, _ = note.get_placement()
        assert note.dxf.text == '16" back'
        assert alignment == TextEntityAlignment.MIDDLE_CENTER
        assert tuple(position) == (110, middle_height - 0.25 * scale, 0)
        assert note.dxf.style == "FF_TEXT"
        assert note.dxf.height == 0.09375 * scale


def test_without_faces_keeps_single_outline_and_null_has_identical_dxf(monkeypatch):
    monkeypatch.setattr(ezdxf.options, "write_fixed_meta_data_for_testing", True)
    elevation = PayloadElevation.model_validate(ELEVATION)
    assert "faces" not in elevation.model_dump(exclude_defaults=True)
    msp = make_elevation_doc(elevation, ROOM).modelspace()
    assert _rectangles(msp) == [[(0, 0), (240, 0), (240, 96), (0, 96)]]
    assert not list(msp.query('TEXT[layer=="DIMENSIONS"]'))
    explicit_null = PayloadElevation.model_validate({**ELEVATION, "faces": None})
    assert build_elevation_dxf(elevation, ROOM) == build_elevation_dxf(explicit_null, ROOM)


def test_faces_validate_shape_and_fit_with_tolerance():
    for patch in (
        {"dx": 200, "length": 60},  # Anchor: face ends at 260 in a 240 elevation.
        {"dx": 160 + 2e-6}, {"height": 96 + 2e-6},
        {"dx": -1}, {"length": 0}, {"height": 0},
        {"note": ""}, {"side": "left"}, {"unknown": 1},
    ):
        with pytest.raises(ValidationError):
            PayloadElevation.model_validate({**ELEVATION, "faces": [{**FACES[0], **patch}]})
    for field in ("key", "wallId", "side", "wallLabel", "dx", "depth", "length", "height"):
        face = {key: value for key, value in FACES[0].items() if key != field}
        with pytest.raises(ValidationError):
            PayloadElevation.model_validate({**ELEVATION, "faces": [face]})
    for patch in ({"dx": 160 + 0.5e-6}, {"height": 96 + 0.5e-6}, {"depth": 16, "note": '16" out'}):
        PayloadElevation.model_validate({**ELEVATION, "faces": [{**FACES[0], **patch}]})


def test_hidden_edge_spans_leave_the_seam_out_of_both_faces():
    """CS3 (Kyle 2026-10-23): a soffit or crown across a seam hides both faces' edges there."""
    faces = copy.deepcopy(FACES)
    faces[1]["hiddenEdges"] = {"left": [{"bottom": 84, "top": 96}], "right": [{"bottom": 84, "top": 96}]}
    faces[2]["hiddenEdges"] = {"left": [{"bottom": 30, "top": 40}, {"bottom": 84, "top": 96}]}
    elevation = PayloadElevation.model_validate({**ELEVATION, "faces": faces})
    msp = make_elevation_doc(elevation, ROOM, 24).modelspace()
    assert [list(r.get_points("xy")) for r in msp.query('LWPOLYLINE[layer=="WALLS"]')] == [
        [(0, 0), (80, 0), (80, 96), (0, 96)],
    ]
    lines = sorted(
        tuple(round(value, 6) for value in (line.dxf.start.x, line.dxf.start.y, line.dxf.end.x, line.dxf.end.y))
        for line in msp.query('LINE[layer=="WALLS"]')
    )
    assert lines == sorted([
        (80, 0, 140, 0), (80, 96, 140, 96), (80, 0, 80, 84), (140, 0, 140, 84),
        (140, 0, 240, 0), (140, 96, 240, 96), (140, 0, 140, 30), (140, 40, 140, 84), (240, 0, 240, 96),
    ])


def test_hidden_edge_span_must_run_upward():
    faces = copy.deepcopy(FACES)
    faces[1]["hiddenEdges"] = {"left": [{"bottom": 96, "top": 84}]}
    with pytest.raises(ValidationError):
        PayloadElevation.model_validate({**ELEVATION, "faces": faces})
