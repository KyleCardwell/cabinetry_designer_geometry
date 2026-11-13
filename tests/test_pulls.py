"""Pull payload, visible circular outlines and PDF anchors (SPEC-HP5 step c)."""

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
from src.drawing.models import DrawingPayload, PayloadPull


FACE = {
    "id": "face", "kind": "face", "x": 10, "z": 4, "width": 15, "height": 30,
    "back": 24, "front": 25, "coversBoxEdges": True,
}
BAR = [
    [23.6875, 27.9375], [23.6875, 32.3125, 1],
    [23.3125, 32.3125], [23.3125, 27.9375, 1],
]
KNOB = [[24.125, 31.875, 1], [22.875, 31.875, 1]]
PULL = {"partId": "face", "outlines": [BAR]}
BAR_LINES = [
    ((23.6875, 27.9375), (23.6875, 32.3125)),
    ((23.3125, 32.3125), (23.3125, 27.9375)),
]


def _payload(parts=None, pulls=None):
    return copy.deepcopy({
        "payloadVersion": 1, "units": "in", "room": {"id": "room", "name": "Room"},
        "elevations": [{
            "key": "wall:front", "letter": "A", "wallId": "wall", "side": "front",
            "title": "Elevation A", "wallLabel": "Wall A", "length": 48, "height": 96,
            "parts": parts if parts is not None else [FACE],
            "pulls": pulls if pulls is not None else [PULL],
        }],
    })


def _doc(payload):
    model = DrawingPayload.model_validate(payload)
    return make_elevation_doc(model.elevations[0], model.room)


def _segments(doc, layer):
    return [(tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2])
            for line in doc.modelspace().query(f'LINE[layer=="{layer}"]')]


def _arcs(doc):
    return list(doc.modelspace().query('ARC[layer=="PULLS"]'))


def _assert_arc(arc, center, radius, start, end):
    assert tuple(arc.dxf.center)[:2] == pytest.approx(center)
    assert arc.dxf.radius == pytest.approx(radius)
    assert arc.dxf.start_angle == pytest.approx(start)
    assert arc.dxf.end_angle == pytest.approx(end)


def test_vertical_bar_has_two_lines_two_true_arcs_and_solid_black_layer():
    doc = _doc(_payload())
    assert _segments(doc, "PULLS") == BAR_LINES
    arcs = _arcs(doc)
    assert len(arcs) == 2
    _assert_arc(arcs[0], (23.5, 32.3125), 0.1875, 0, 180)
    _assert_arc(arcs[1], (23.5, 27.9375), 0.1875, 180, 0)
    layer = doc.layers.get("PULLS")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (7, "CONTINUOUS", 13)
    assert len(_segments(doc, "FACES")) == 4
    assert _segments(doc, "HIDDEN") == []


def test_two_point_knob_is_a_complete_circle_without_lines():
    doc = _doc(_payload(pulls=[{"partId": "face", "outlines": [KNOB]}]))
    assert _segments(doc, "PULLS") == []
    arcs = _arcs(doc)
    assert len(arcs) in (1, 2)
    sweep = 0
    for arc in arcs:
        assert tuple(arc.dxf.center)[:2] == pytest.approx((23.5, 31.875))
        assert arc.dxf.radius == pytest.approx(0.625)
        sweep += (arc.dxf.end_angle - arc.dxf.start_angle) % 360 or 360
    assert sweep == pytest.approx(360)


def test_nearer_cover_clips_bar_at_30_and_drops_hidden_pull_segments():
    shade = {**FACE, "id": "shade", "kind": "panel", "z": 30, "height": 4,
             "back": 25, "front": 26}
    doc = _doc(_payload(parts=[FACE, shade]))
    assert _segments(doc, "PULLS") == [
        ((23.6875, 27.9375), (23.6875, 30)),
        ((23.3125, 30), (23.3125, 27.9375)),
    ]
    assert len(_arcs(doc)) == 1
    _assert_arc(_arcs(doc)[0], (23.5, 27.9375), 0.1875, 180, 0)
    without = _doc(_payload(parts=[FACE, shade], pulls=[]))
    assert _segments(doc, "HIDDEN") == _segments(without, "HIDDEN")
    assert list(doc.modelspace().query('ARC[layer=="HIDDEN"]')) == []
    for change in ({"opaque": False}, {"front": FACE["front"]}):
        visible = _doc(_payload(parts=[FACE, {**shade, **change}]))
        assert _segments(visible, "PULLS") == BAR_LINES
        assert len(_arcs(visible)) == 2


def test_pull_validation_checks_ids_outlines_bulges_and_unknown_keys():
    with pytest.raises(ValidationError, match="Pulls name unknown part ids: nope"):
        DrawingPayload.model_validate(_payload(pulls=[{**PULL, "partId": "nope"}]))
    for pull in (
        {**PULL, "partId": ""}, {"partId": "face"}, {**PULL, "color": "red"},
        {**PULL, "outlines": []}, {**PULL, "outlines": [[]]},
        {**PULL, "outlines": [[[1, 2]]]},
        {**PULL, "outlines": [[[1, 2], [2, 3]]]},
        {**PULL, "outlines": [[[1, 2], [2, 3], [3, 4]]]},
        {**PULL, "outlines": [BAR, [[1, 2]]]},
        *({**PULL, "outlines": [[[1, 2, bulge], [2, 3, 1]]]}
          for bulge in (1.1, -1.1, float("inf"), float("nan"))),
    ):
        with pytest.raises(ValidationError):
            DrawingPayload.model_validate(_payload(pulls=[pull]))
    rounded = PayloadPull(partId="face", outlines=[[[1, 2, 0.1234567], [2, 3, 1]]])
    assert rounded.outlines[0][0][2] == 0.123457


def test_omitted_pulls_default_to_empty_and_preserve_dxf(monkeypatch):
    monkeypatch.setattr(ezdxf.options, "write_fixed_meta_data_for_testing", True)
    payload = _payload(pulls=[])
    del payload["elevations"][0]["pulls"]
    model = DrawingPayload.model_validate(payload)
    assert model.elevations[0].pulls == []
    assert json.loads(model.model_dump_json(exclude_defaults=True)) == payload
    explicit = DrawingPayload.model_validate(_payload(pulls=[]))
    assert build_elevation_dxf(model.elevations[0], model.room) == build_elevation_dxf(
        explicit.elevations[0], explicit.room,
    )
    doc = _doc(payload)
    assert _segments(doc, "PULLS") == _arcs(doc) == []
    assert _segments(doc, "FACES") == [
        ((10, 4), (25, 4)), ((25, 4), (25, 34)),
        ((25, 34), (10, 34)), ((10, 34), (10, 4)),
    ]
    assert _segments(doc, "HIDDEN") == []


def test_multiple_outlines_and_repeated_part_entries_do_not_hide_other_geometry():
    tab = [[12, 10], [16, 10], [16, 10.5], [12, 10.5]]
    horizontal = [[12, 20], [16, 20, 1], [16, 20.5], [12, 20.5, 1]]
    behind = {**FACE, "id": "behind", "kind": "cabinet", "front": 23, "back": 22}
    payload = _payload(parts=[{**FACE, "opaque": False}, behind], pulls=[
        {"partId": "face", "outlines": [BAR, KNOB]},
        {"partId": "face", "outlines": [tab, horizontal]},
    ])
    elevation = payload["elevations"][0]
    elevation["doorDetails"] = [{"partId": "behind", "openings": [
        {"x": 11, "z": 5, "width": 13, "height": 28},
    ]}]
    elevation["swingMarks"] = [{"partId": "behind", "lines": [
        {"x1": 10, "z1": 4, "x2": 25, "z2": 34},
    ]}]
    doc = _doc(payload)
    assert _segments(doc, "PULLS") == [
        *BAR_LINES,
        ((12, 10), (16, 10)), ((16, 10), (16, 10.5)),
        ((16, 10.5), (12, 10.5)), ((12, 10.5), (12, 10)),
        ((12, 20), (16, 20)), ((16, 20.5), (12, 20.5)),
    ]
    assert len(_arcs(doc)) == 6
    _assert_arc(_arcs(doc)[-2], (16, 20.25), 0.25, 270, 90)
    _assert_arc(_arcs(doc)[-1], (12, 20.25), 0.25, 90, 270)
    elevation["pulls"] = []
    without = _doc(payload)
    for layer in ("FACES", "CABINETS", "HIDDEN", "DOOR_DETAILS", "SWING_MARKS"):
        assert _segments(doc, layer) == _segments(without, layer)


def test_bundle_pdf_frontend_draws_pull_lines_and_arcs(monkeypatch):
    rendered = []

    def record(original):
        def draw_entity(frontend, entity, properties):
            if properties.layer == "PULLS":
                rendered.append(entity.dxftype())
                assert properties.lineweight == pytest.approx(0.13)
            return original(frontend, entity, properties)
        return draw_entity

    monkeypatch.setattr(Frontend, "draw_line_entity", record(Frontend.draw_line_entity))
    monkeypatch.setattr(Frontend, "draw_curve_entity", record(Frontend.draw_curve_entity))
    payload = _payload()
    result = draw(payload)
    with ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as archive:
        assert json.loads(archive.read("payload.json")) == payload
        doc = ezdxf.read(io.StringIO(archive.read("elevation-A.dxf").decode("utf-8")))
        assert _segments(doc, "PULLS") == BAR_LINES
        assert len(_arcs(doc)) == 2
        reader = PdfReader(io.BytesIO(archive.read("drawings.pdf")))
    assert sorted(rendered) == ["ARC", "ARC", "LINE", "LINE"]
    assert len(reader.pages) == 1
    operations = ContentStream(reader.pages[0].get_contents(), reader).operations
    assert any(float(args[0]) == pytest.approx(0.13 * 72 / 25.4)
               for args, op in operations if op == b"w")
    assert any(op == b"S" for _, op in operations)
