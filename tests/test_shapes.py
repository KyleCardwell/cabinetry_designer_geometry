"""Accessory shape payload, room/group depth occlusion and PDF anchors (SH4 b)."""

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

from src.drawing.arcs import flatten_outline
from src.drawing.bundle import draw
from src.drawing.elevation_dxf import build_elevation_dxf, make_elevation_doc
from src.drawing.models import DrawingPayload
from src.dxf.writer import ACCESSORY_LAYER_DEFS


CAB = {
    "id": "cab", "kind": "cabinet", "x": 100, "z": 10, "width": 36, "height": 80,
    "back": 0, "front": 24, "coversBoxEdges": False,
}
ROD = [
    {"closed": True, "points": [[100, 74.5], [103, 74.5], [103, 77.5], [100, 77.5]]},
    {"closed": True, "points": [[133, 74.5], [136, 74.5], [136, 77.5], [133, 77.5]]},
    {"closed": True, "points": [[100.875, 76, 1], [102.125, 76, 1]]},
    {"closed": True, "points": [[133.875, 76, 1], [135.125, 76, 1]]},
    {"closed": False, "points": [[103, 76.53125], [133, 76.53125]]},
    {"closed": False, "points": [[103, 75.46875], [133, 75.46875]]},
]


def _shape(loops=ROD, depth=10, **kwargs):
    return {"partId": "cab", "kind": "accessory", "depth": depth, "loops": loops, **kwargs}


def _square(x, z, size):
    return {"closed": True, "points": [[x, z], [x + size, z], [x + size, z + size], [x, z + size]]}


A = [_square(110, 30, 10), _square(112, 32, 2)]
B = [_square(115, 35, 10)]


def _payload(shapes=None, parts=None):
    return copy.deepcopy({
        "payloadVersion": 1, "units": "in", "room": {"id": "room", "name": "Room"},
        "elevations": [{
            "key": "wall:front", "letter": "A", "wallId": "wall", "side": "front",
            "title": "Elevation A", "wallLabel": "Wall A", "length": 160, "height": 96,
            "parts": parts if parts is not None else [CAB],
            "shapes": shapes if shapes is not None else [_shape()],
        }],
    })


def _doc(payload):
    model = DrawingPayload.model_validate(payload)
    return make_elevation_doc(model.elevations[0], model.room)


def _normalized(segments):
    return sorted(tuple(sorted(tuple(round(v, 6) for v in p) for p in segment)) for segment in segments)


def _segments(doc, layer="ACCESSORIES"):
    return _normalized((tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2])
                       for line in doc.modelspace().query(f'LINE[layer=="{layer}"]'))


def _loop_segments(loops):
    return [(a[:2], b[:2]) for loop in loops
            for a, b in zip(loop["points"], loop["points"][1:] + (loop["points"][:1] if loop["closed"] else []))]


def _arcs(doc, layer="ACCESSORIES"):
    return list(doc.modelspace().query(f'ARC[layer=="{layer}"]'))


def test_rod_anchor_has_ten_lines_four_true_arcs_and_accessories_layer():
    doc = _doc(_payload())
    assert _segments(doc) == _normalized(_loop_segments([*ROD[:2], *ROD[4:]]))
    assert len(_segments(doc)) == 10
    arcs = _arcs(doc)
    assert len(arcs) == 4
    for center in ((101.5, 76), (134.5, 76)):
        hole = [arc for arc in arcs if tuple(arc.dxf.center)[:2] == pytest.approx(center)]
        assert len(hole) == 2
        assert all(arc.dxf.radius == pytest.approx(0.625) for arc in hole)
        assert sum((arc.dxf.end_angle - arc.dxf.start_angle) % 360 for arc in hole) == pytest.approx(360)
    layer = doc.layers.get("ACCESSORIES")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (7, "CONTINUOUS", 13)
    assert _segments(doc, "HIDDEN") == _arcs(doc, "HIDDEN") == []


def test_rail_anchor_clips_at_76_and_drops_hidden_geometry():
    rail = {**CAB, "id": "rail", "kind": "frame", "z": 74, "height": 2, "front": 24.8125}
    doc = _doc(_payload(parts=[CAB, rail]))
    assert _segments(doc) == _normalized([
        ((103, 76.53125), (133, 76.53125)),
        *[(a, b) for left, right in ((100, 103), (133, 136)) for a, b in (
            ((left, 76), (left, 77.5)), ((left, 77.5), (right, 77.5)),
            ((right, 77.5), (right, 76)),
        )],
    ])
    assert len(_arcs(doc)) == 2
    assert all(arc.dxf.start_angle == pytest.approx(0)
               and arc.dxf.end_angle == pytest.approx(180) for arc in _arcs(doc))
    without = _doc(_payload(parts=[CAB, rail], shapes=[]))
    assert _segments(doc, "HIDDEN") == _segments(without, "HIDDEN")
    assert _arcs(doc, "HIDDEN") == []
    for change in ({"opaque": False}, {"front": CAB["front"]}):
        visible = _doc(_payload(parts=[CAB, {**rail, **change}]))
        assert len(_segments(visible)) == 10
        assert len(_arcs(visible)) == 4


def test_square_anchor_nearer_swapped_and_equal_depths():
    a, b = _loop_segments(A), _loop_segments(B)
    clipped_b = [((120, 35), (125, 35)), ((125, 35), (125, 45)),
                 ((125, 45), (115, 45)), ((115, 45), (115, 40))]
    clipped_a = [((110, 30), (120, 30)), ((120, 30), (120, 35)),
                 ((115, 40), (110, 40)), ((110, 40), (110, 30)), *_loop_segments(A[1:])]
    for depths, expected in [((2, 6), a + clipped_b), ((6, 2), clipped_a + b),
                             ((2, 2), a + b), ((2, 2.0000005), a + b)]:
        doc = _doc(_payload(shapes=[_shape(A, depths[0]), _shape(B, depths[1])]))
        assert _segments(doc) == _normalized(expected)
        assert _segments(doc, "HIDDEN") == []


def test_open_only_anchor_hides_nothing():
    open_b = [{"closed": False, "points": B[0]["points"] + B[0]["points"][:1]}]
    doc = _doc(_payload(shapes=[_shape(A, 6), _shape(open_b, 2)]))
    assert _segments(doc) == _normalized(_loop_segments(A) + _loop_segments(open_b))


def test_outer_loops_are_solid_and_shapes_only_hide_their_own_part_group():
    # The inner loop does not punch a transparent hole in the outer loop's area.
    inside = [_square(112.5, 32.5, 1)]
    doc = _doc(_payload(shapes=[_shape(A, 2), _shape(inside, 6)]))
    assert _segments(doc) == _normalized(_loop_segments(A))
    other = {**CAB, "id": "other", "front": 23, "opaque": False}
    payload = _payload(parts=[{**CAB, "opaque": False}, other], shapes=[
        _shape(A, 2), _shape(inside, 6, partId="other"),
    ])
    elevation = payload["elevations"][0]
    elevation["interiors"] = [{"partId": "other", "lines": [
        {"x1": 111, "z1": 33, "x2": 119, "z2": 33},
    ], "labels": [{"text": "Rod", "x": 110, "z": 30, "width": 10, "height": 10}]}]
    elevation["pulls"] = [{"partId": "other", "outlines": [inside[0]["points"]]}]
    doc = _doc(payload)
    assert _segments(doc) == _normalized(_loop_segments(A) + _loop_segments(inside))
    elevation["shapes"] = []
    without = _doc(payload)
    for layer in ("CABINETS", "INTERIORS", "PULLS", "HIDDEN"):
        assert _segments(doc, layer) == _segments(without, layer)
    assert [e.dxf.text for e in doc.modelspace().query('TEXT[layer=="INTERIORS"]')] == ["Rod"]


def test_open_arcs_never_close_and_rejoin_after_clipping():
    for bulge, angles in ((1, (180, 270)), (-1, (90, 180))):
        loop = {"closed": False, "points": [[110, 40, bulge], [120, 40, 1]]}
        points, sources = flatten_outline(loop["points"], closed=False)
        assert points[0] == (110, 40) and points[-1] == (120, 40)
        assert len(sources) == 1  # The final point's bulge has no outgoing segment.
        cover = {**CAB, "id": "cover", "kind": "panel", "x": 115, "z": 20,
                 "width": 10, "height": 40, "front": 25}
        doc = _doc(_payload(parts=[CAB, cover], shapes=[_shape([loop])]))
        assert _segments(doc) == []
        arc, = _arcs(doc)
        assert tuple(arc.dxf.center)[:2] == pytest.approx((115, 40))
        assert arc.dxf.radius == pytest.approx(5)
        assert (arc.dxf.start_angle, arc.dxf.end_angle) == pytest.approx(angles)
        assert _arcs(doc, "HIDDEN") == []


def test_invalid_shape_anchor_and_nested_payload_validation():
    block = {"name": "SHAPE_CLOSET_ROD_3F9A2C", "x": 100, "z": 76, "mirror": False}
    invalid = [
        _shape(partId="nope"), _shape(kind="appliance"), _shape(extra=True),
        _shape(block={**block, "name": "shape rod"}),
        _shape(block={**block, "name": "A" * 65}),
        _shape(block={**block, "extra": True}),
        _shape(loops=[]), _shape(depth=float("nan")),
        *[_shape([{"closed": closed, "points": [[1, 2]]}]) for closed in (True, False)],
        _shape([{"closed": True, "points": [[1, 2], [2, 3]]}]),
        _shape([{"closed": False, "points": [[1, 2], [2, 3]], "extra": True}]),
        *[_shape([{"closed": True, "points": [[1, 2, bulge], [2, 3, 1]]}])
          for bulge in (1.1, -1.1, float("inf"), float("nan"))],
    ]
    for shape in invalid:
        with pytest.raises(ValidationError):
            DrawingPayload.model_validate(_payload(shapes=[shape]))
    rounded = DrawingPayload.model_validate(_payload(shapes=[_shape([
        {"closed": True, "points": [[1, 2, 0.1234567], [2, 3, 1]]},
    ])]))
    assert rounded.elevations[0].shapes[0].loops[0].points[0][2] == 0.123457


def test_block_metadata_is_stored_but_still_drawn_as_plain_geometry():
    block = {"name": "SHAPE_CLOSET_ROD_3F9A2C", "x": 100, "z": 76, "mirror": True}
    payload = _payload(shapes=[_shape(block=block)])
    model = DrawingPayload.model_validate(payload)
    assert model.elevations[0].shapes[0].block.model_dump() == block
    doc = _doc(payload)
    assert _segments(doc) == _segments(_doc(_payload()))
    assert len(_arcs(doc)) == 4
    assert not list(doc.modelspace().query('INSERT[layer=="ACCESSORIES"]'))
    assert block["name"] not in doc.blocks


def test_omitted_shapes_preserve_payload_and_preexisting_dxf_bytes(monkeypatch):
    monkeypatch.setattr(ezdxf.options, "write_fixed_meta_data_for_testing", True)
    payload = _payload(shapes=[])
    del payload["elevations"][0]["shapes"]
    model = DrawingPayload.model_validate(payload)
    assert model.elevations[0].shapes == []
    assert json.loads(model.model_dump_json(exclude_defaults=True)) == payload
    omitted = build_elevation_dxf(model.elevations[0], model.room)
    explicit = DrawingPayload.model_validate(_payload(shapes=[]))
    assert omitted == build_elevation_dxf(explicit.elevations[0], explicit.room)
    assert "ACCESSORIES" not in _doc(payload).layers
    # The previous layer registry produces exactly the same serialized document.
    monkeypatch.delitem(ACCESSORY_LAYER_DEFS, "ACCESSORIES")
    assert omitted == build_elevation_dxf(model.elevations[0], model.room)


def test_rod_anchor_pdf_uses_the_same_lines_and_arcs(monkeypatch):
    rendered = []

    def record(original):
        def draw_entity(frontend, entity, properties):
            if properties.layer == "ACCESSORIES":
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
        assert len(_segments(doc)) == 10 and len(_arcs(doc)) == 4
        reader = PdfReader(io.BytesIO(archive.read("drawings.pdf")))
    assert sorted(rendered) == ["ARC"] * 4 + ["LINE"] * 10
    assert len(reader.pages) == 1
    assert "SCALE" in reader.pages[0].extract_text()
