"""Interior and glass-mark validation, visibility and text anchors (SPEC-IN14 step f)."""

import json
from pathlib import Path

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from pydantic import ValidationError

from src.drawing.elevation_dxf import build_elevation_dxf, make_elevation_doc
from src.drawing.models import DrawingPayload, PayloadElevation, PayloadRoom


CABINET = {
    "id": "c", "kind": "cabinet", "x": 0, "z": 0, "width": 24, "height": 30,
    "back": 0, "front": 24, "coversBoxEdges": False,
}
FACE = {
    "id": "c:r", "kind": "face", "x": 0, "z": 15, "width": 24, "height": 15,
    "back": 24, "front": 24.75, "coversBoxEdges": True,
}
HOLE = {"x": 3, "z": 18, "width": 18, "height": 9}
INTERIOR = {"partId": "c", "lines": [
    {"x1": 1, "z1": 10, "x2": 23, "z2": 10},
    {"x1": 1, "z1": 20, "x2": 23, "z2": 20},
]}
ROOM = PayloadRoom(id="room", name="Room")


def _elevation(parts=None, interiors=None, glass_marks=None):
    return PayloadElevation.model_validate({
        "key": "wall:front", "letter": "A", "wallId": "wall", "side": "front",
        "title": "Elevation A", "wallLabel": "Wall A", "length": 96, "height": 96,
        "parts": parts if parts is not None else [CABINET],
        "interiors": interiors if interiors is not None else [INTERIOR],
        "glassMarks": glass_marks if glass_marks is not None else [],
    })


def _doc(parts=None, interiors=None, glass_marks=None, plot_scale=24):
    return make_elevation_doc(_elevation(parts, interiors, glass_marks), ROOM, plot_scale)


def _segments(doc, layer):
    return [(tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2])
            for line in doc.modelspace().query(f'LINE[layer=="{layer}"]')]


def test_open_cabinet_shows_both_interior_lines_without_extra_outlines_or_occlusion():
    doc = _doc()
    assert _segments(doc, "INTERIORS") == [((1, 10), (23, 10)), ((1, 20), (23, 20))]
    assert _segments(doc, "HIDDEN") == []
    layer = doc.layers.get("INTERIORS")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (7, "CONTINUOUS", 9)
    # Interior shapes neither outline their bounds nor hide geometry behind them.
    behind = {**CABINET, "id": "behind", "front": 12, "opaque": False}
    parts = [{**CABINET, "opaque": False}, behind]
    with_interiors = _doc(parts)
    without_interiors = _doc(parts, interiors=[])
    for layer in ("CABINETS", "HIDDEN"):
        assert _segments(with_interiors, layer) == _segments(without_interiors, layer)


def test_nearer_faces_and_frames_drop_covered_interior_lines_without_hidden_segments():
    for kind in ("face", "frame"):
        parts = [CABINET, {**FACE, "kind": kind}]
        doc = _doc(parts)
        assert _segments(doc, "INTERIORS") == [((1, 10), (23, 10))]
        assert _segments(doc, "HIDDEN") == _segments(_doc(parts, interiors=[]), "HIDDEN")


def test_face_hole_shows_only_the_interior_segment_inside_the_opening():
    doc = _doc([CABINET, {**FACE, "holes": [HOLE]}])
    assert _segments(doc, "INTERIORS") == [((1, 10), (23, 10)), ((3, 20), (21, 20))]


def test_face_glass_mark_draws_on_the_finest_continuous_layer_without_occlusion():
    parts = [CABINET, {**FACE, "holes": [HOLE]}]
    marks = [{"partId": "c:r", "lines": [{"x1": 10, "z1": 20, "x2": 14, "z2": 24}]}]
    doc = _doc(parts, glass_marks=marks)
    assert _segments(doc, "GLASS_MARKS") == [((10, 20), (14, 24))]
    layer = doc.layers.get("GLASS_MARKS")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (7, "CONTINUOUS", 9)
    without_marks = _doc(parts)
    for layer in ("CABINETS", "FACES", "INTERIORS", "HIDDEN"):
        assert _segments(doc, layer) == _segments(without_marks, layer)


def test_cabinet_clips_window_glass_marks_and_drops_the_hidden_segments():
    window = {
        "id": "w1", "kind": "opening", "x": 40, "z": 36, "width": 36, "height": 48,
        "back": -4.5, "front": 0, "coversBoxEdges": False,
    }
    cover = {**CABINET, "id": "cover", "x": 40, "z": 36, "width": 36, "height": 24}
    marks = [{"partId": "w1", "lines": [
        {"x1": 50, "z1": 54, "x2": 62, "z2": 66},
        {"x1": 48, "z1": 62, "x2": 54, "z2": 68},
        {"x1": 60, "z1": 42, "x2": 66, "z2": 48},
    ]}]
    parts = [CABINET, window, cover]
    doc = _doc(parts, glass_marks=marks)
    assert _segments(doc, "GLASS_MARKS") == [((56, 60), (62, 66)), ((48, 62), (54, 68))]
    assert _segments(doc, "HIDDEN") == _segments(_doc(parts), "HIDDEN")


def test_interior_labels_fit_the_box_and_use_centred_paper_scaled_text():
    label = {"text": "Fixed rod", "x": 1, "z": 5, "width": 22, "height": 1.25}

    def labels(change=None, scale=24):
        doc = _doc(interiors=[{**INTERIOR, "labels": [{**label, **(change or {})}]}], plot_scale=scale)
        return list(doc.modelspace().query('TEXT[layer=="INTERIORS"]'))

    assert labels() == []  # 1.25 < 2.25 inches at plot scale 24.
    [text] = labels({"height": 3})
    assert (text.dxf.text, text.dxf.style, text.dxf.height) == ("Fixed rod", "FF_TEXT", 2.25)
    alignment, point, _ = text.get_placement()
    assert alignment == TextEntityAlignment.MIDDLE_CENTER
    assert tuple(point)[:2] == (12, 6.5)
    min_width = 0.6 * 2.25 * len(label["text"])
    assert labels({"height": 3, "width": min_width - 0.001}) == []
    assert len(labels({"height": 2.25, "width": min_width})) == 1
    [smaller] = labels(scale=12)
    assert smaller.dxf.height == 1.125


def test_interior_and_glass_models_reject_unknown_parts_invalid_records_and_extra_keys():
    for key, message in (("interiors", "Interiors"), ("glass_marks", "Glass marks")):
        with pytest.raises(ValidationError, match=f"{message} name unknown part ids: nope"):
            _elevation(**{key: [{**INTERIOR, "partId": "nope"}]})
        for record in (
            {**INTERIOR, "partId": ""}, {**INTERIOR, "lines": []}, {"partId": "c"},
            {**INTERIOR, "color": "red"},
            {**INTERIOR, "lines": [{**INTERIOR["lines"][0], "color": "red"}]},
        ):
            with pytest.raises(ValidationError):
                _elevation(**{key: [record]})
    label = {"text": "Rod", "x": 1, "z": 5, "width": 22, "height": 3}
    for change in ({"text": ""}, {"width": 0}, {"height": 0}, {"width": -1},
                   {"height": -1}, {"color": "red"}):
        with pytest.raises(ValidationError):
            _elevation(interiors=[{**INTERIOR, "labels": [{**label, **change}]}])
    assert _elevation().interiors[0].labels == []


def test_existing_fixtures_default_to_empty_collections_and_preserve_dxf(monkeypatch):
    monkeypatch.setattr(ezdxf.options, "write_fixed_meta_data_for_testing", True)
    for path in sorted((Path(__file__).parent / "fixtures").glob("*payload.json")):
        raw = json.loads(path.read_text())
        payload = DrawingPayload.model_validate(raw)
        for elevation, original in zip(payload.elevations, raw["elevations"]):
            assert "interiors" not in original and "glassMarks" not in original
            assert elevation.interiors == elevation.glassMarks == []
            explicit = PayloadElevation.model_validate({**original, "interiors": [], "glassMarks": []})
            scale = payload.plotScale or 24
            assert build_elevation_dxf(elevation, payload.room, scale) == build_elevation_dxf(
                explicit, payload.room, scale,
            )
            doc = make_elevation_doc(elevation, payload.room, scale)
            assert _segments(doc, "INTERIORS") == _segments(doc, "GLASS_MARKS") == []
            assert list(doc.modelspace().query('TEXT[layer=="INTERIORS"]')) == []
