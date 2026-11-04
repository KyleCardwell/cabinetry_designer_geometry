"""SH7 step e: leg payloads, depth occlusion, blocks, plan arcs and PDF."""

import base64
import copy
import io
from zipfile import ZipFile

import ezdxf
import pytest
from ezdxf.addons.drawing import Frontend
from pydantic import ValidationError
from pypdf import PdfReader

from src.drawing.bundle import draw
from src.drawing.elevation_dxf import build_elevation_dxf, make_elevation_doc
from src.drawing.models import DrawingPayload, PayloadPlan, PayloadPlanPart, PayloadPlanShape, PayloadRoom
from src.drawing.plan_dxf import build_plan_dxf, make_plan_doc
from src.dxf.writer import LEG_LAYER_DEFS


ROOM = PayloadRoom(id="room", name="Room")
DOOR = {
    "id": "door", "kind": "face", "x": 0, "z": 4, "width": 30, "height": 30,
    "back": 24, "front": 24.875, "coversBoxEdges": False,
}
LEG = {
    "id": "leg", "kind": "leg", "x": 10, "z": 0, "width": 3.5, "height": 34.5,
    "back": 21.875, "front": 25.375, "coversBoxEdges": False, "opaque": False,
    "openEdges": ["left", "right", "top", "bottom"],
}
CABINET = {
    "id": "cabinet", "kind": "cabinet", "top": 34.5,
    "points": [[0, 0], [30, 0], [30, 24], [0, 24]],
}


def _rectangle(x=10, y=0, width=3.5, height=34.5):
    return {"closed": True, "points": [
        [x, y], [x + width, y], [x + width, y + height], [x, y + height],
    ]}


def _record(**changes):
    return {"partId": "leg", "kind": "leg", "depth": 0, "loops": [_rectangle()], **changes}


def _payload(parts=None, shapes=None):
    return copy.deepcopy({
        "payloadVersion": 1, "units": "in", "room": ROOM.model_dump(exclude_defaults=True),
        "elevations": [{
            "key": "wall:front", "letter": "A", "wallId": "wall", "side": "front",
            "title": "Elevation A", "wallLabel": "Wall A", "length": 60, "height": 96,
            "parts": [DOOR, LEG] if parts is None else parts,
            "shapes": [_record()] if shapes is None else shapes,
        }],
    })


def _doc(payload):
    model = DrawingPayload.model_validate(payload)
    return make_elevation_doc(model.elevations[0], model.room)


def _normalized(segments):
    return sorted(tuple(sorted(tuple(round(v, 6) for v in point) for point in segment))
                  for segment in segments)


def _segments(doc, layer="LEGS"):
    return _normalized((tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2])
                       for line in doc.modelspace().query(f'LINE[layer=="{layer}"]'))


def _edges(loop):
    points = loop["points"]
    return list(zip(points, points[1:] + (points[:1] if loop["closed"] else [])))


def _circle(x, y, top=34.5):
    return {"id": "circle", "kind": "leg", "top": top, "loops": [
        {"closed": True, "points": [[x - 1.75, y, 1], [x + 1.75, y, 1]]},
    ]}


def test_proud_leg_anchor_clips_door_and_hides_all_deeper_details():
    payload = _payload()
    doc = _doc(payload)
    assert _segments(doc) == _normalized(_edges(_rectangle()))
    assert _segments(doc, "FACES") == _normalized([
        ((0, 4), (10, 4)), ((13.5, 4), (30, 4)),
        ((0, 34), (10, 34)), ((13.5, 34), (30, 34)),
        ((0, 4), (0, 34)), ((30, 4), (30, 34)),
    ])
    # Only the door's hidden edges are dashed; the leg contributes none.
    assert _segments(doc, "HIDDEN") == _normalized([
        ((10, 4), (13.5, 4)), ((10, 34), (13.5, 34)),
    ])
    layer = doc.layers.get("LEGS")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (7, "CONTINUOUS", 18)
    assert "ACCESSORIES" not in doc.layers

    elevation = payload["elevations"][0]
    line = {"x1": 11, "z1": 10, "x2": 12, "z2": 10}
    elevation["interiors"] = [{"partId": "door", "lines": [line]}]
    elevation["pulls"] = [{"partId": "door", "outlines": [
        _rectangle(11, 10, 1, 1)["points"],
    ]}]
    elevation["shapes"].append({
        "partId": "door", "kind": "accessory", "depth": 0,
        "loops": [_rectangle(11, 10, 1, 1)],
    })
    doc = _doc(payload)
    for layer in ("INTERIORS", "PULLS", "ACCESSORIES"):
        assert not list(doc.modelspace().query(f'*[layer=="{layer}"]'))

    # Leg opacity also clips the visible fill of room sections.
    section = _doc(_payload(parts=[{**DOOR, "kind": "section"}, LEG]))
    hatches = list(section.modelspace().query('HATCH[layer=="SECTIONS"]'))
    assert len(hatches) == 2
    assert sorted((min(x for x, y, bulge in hatch.paths[0].vertices),
                   max(x for x, y, bulge in hatch.paths[0].vertices))
                  for hatch in hatches) == [(0, 10), (13.5, 30)]


def test_rear_leg_anchor_keeps_only_bits_below_four_and_above_thirty_four():
    doc = _doc(_payload(parts=[DOOR, {**LEG, "front": 3.5, "back": 0}]))
    assert _segments(doc) == _normalized([
        ((10, 0), (13.5, 0)), ((10, 0), (10, 4)), ((13.5, 0), (13.5, 4)),
        ((10, 34.5), (13.5, 34.5)), ((10, 34), (10, 34.5)), ((13.5, 34), (13.5, 34.5)),
    ])
    assert _segments(doc, "FACES") == _normalized(_edges(_rectangle(0, 4, 30, 30)))
    assert _segments(doc, "HIDDEN") == []


def test_two_leg_anchor_drops_entire_rear_leg_independent_of_record_order():
    front = {**LEG, "front": 24.875}
    back = {**LEG, "id": "back", "front": 3.5, "back": 0}
    records = [_record(), _record(partId="back")]
    for shapes in (records, records[::-1]):
        doc = _doc(_payload(parts=[DOOR, front, back], shapes=shapes))
        assert _segments(doc) == _normalized(_edges(_rectangle()))
        assert _segments(doc, "HIDDEN") == []


def test_leg_block_anchor_uses_legs_inserts_reuses_definition_and_clips_fallback():
    block = {"name": "SHAPE_LEG_ABC123", "x": 10, "z": 0, "mirror": False}
    doc = _doc(_payload(shapes=[_record(block=block)]))
    insert, = doc.modelspace().query('INSERT[layer=="LEGS"]')
    assert insert.dxf.name == block["name"]
    assert tuple(insert.dxf.insert)[:2] == (10, 0)
    assert _segments(doc) == []
    definition, = doc.blocks[block["name"]]
    assert definition.closed and definition.dxf.layer == "0"
    assert list(definition.get_points("xy")) == [(0, 0), (3.5, 0), (3.5, 34.5), (0, 34.5)]

    second = {**LEG, "id": "second", "x": 20}
    doc = _doc(_payload(parts=[LEG, second], shapes=[
        _record(partId="second", loops=[_rectangle(20)],
                block={**block, "x": 23.5, "mirror": True}),
        _record(block=block),
    ]))
    assert len(doc.modelspace().query('INSERT[layer=="LEGS"]')) == 2
    assert len(doc.blocks[block["name"]]) == 1
    assert [insert.dxf.xscale for insert in doc.modelspace().query('INSERT[layer=="LEGS"]')] == [-1, 1]

    doc = _doc(_payload(parts=[DOOR, {**LEG, "front": 3.5}], shapes=[_record(block=block)]))
    assert not doc.modelspace().query('INSERT[layer=="LEGS"]')
    assert block["name"] not in doc.blocks
    assert len(_segments(doc)) == 6


def test_plan_circle_anchor_rejoins_arcs_clips_by_height_and_reaches_pdf(monkeypatch):
    plan = {"parts": [CABINET], "shapes": [_circle(35, 12)]}
    doc = make_plan_doc(PayloadPlan.model_validate(plan), ROOM)
    arcs = list(doc.modelspace().query('ARC[layer=="LEGS"]'))
    assert len(arcs) == 2 and _segments(doc) == []
    for arc in arcs:
        assert tuple(arc.dxf.center)[:2] == pytest.approx((35, 12))
        assert arc.dxf.radius == pytest.approx(1.75)
    assert sum((arc.dxf.end_angle - arc.dxf.start_angle) % 360 for arc in arcs) == pytest.approx(360)
    assert doc.layers.get("LEGS").dxf.lineweight == 18
    assert "ACCESSORIES" not in doc.layers
    for top, count in ((4, 0), (34.5, 2)):
        hidden = make_plan_doc(PayloadPlan.model_validate({**plan, "shapes": [_circle(15, 12, top)]}), ROOM)
        assert len(hidden.modelspace().query('ARC[layer=="LEGS"]')) == count
        assert _segments(hidden) == _segments(hidden, "HIDDEN") == []

    # A nearer circular leg also clips the cabinet, and a partly covered circle
    # is rejoined to true ARCs instead of leaving flattened line fragments.
    for top, length, sweep in ((35, 104.5, 360), (4, 108, 180)):
        clipped = make_plan_doc(PayloadPlan.model_validate({
            **plan, "shapes": [_circle(30, 12, top)],
        }), ROOM)
        shown = clipped.modelspace().query('ARC[layer=="LEGS"]')
        assert sum((arc.dxf.end_angle - arc.dxf.start_angle) % 360 for arc in shown) == pytest.approx(sweep)
        assert sum(line.dxf.start.distance(line.dxf.end)
                   for line in clipped.modelspace().query('LINE[layer=="CABINETS"]')) == pytest.approx(length)
        assert _segments(clipped) == []

    rendered = []
    original = Frontend.draw_entity

    def record(frontend, entity, properties):
        if properties.layer == "LEGS":
            rendered.append(entity.dxftype())
            assert properties.lineweight == pytest.approx(0.18)
        return original(frontend, entity, properties)

    monkeypatch.setattr(Frontend, "draw_entity", record)
    payload = _payload()
    payload["plan"] = plan
    result = draw(payload)
    with ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as archive:
        assert len(PdfReader(io.BytesIO(archive.read("drawings.pdf"))).pages) == 2
    assert sorted(rendered) == ["ARC", "ARC", "LINE", "LINE", "LINE", "LINE"]


def test_leg_loop_opacity_and_plan_payload_validation():
    # Inner closed loops do not punch holes; open paths do not create opaque area
    # or an implicit closing edge. This applies in both projections.
    inner = _rectangle(11, 10, 1, 1)
    opened = {"closed": False, "points": [[9, 8], [9, 9], [9.5, 9]]}
    loops = [_rectangle(), inner, opened]
    payload = _payload(parts=[{**LEG, "id": "back", "front": 3.5}, LEG], shapes=[
        _record(partId="back", loops=[_rectangle(11.25, 10.25, 0.5, 0.5)]),
        _record(loops=loops),
    ])
    assert _segments(_doc(payload)) == _normalized([edge for loop in loops for edge in _edges(loop)])
    plan = PayloadPlan.model_validate({"shapes": [
        {"id": "back", "kind": "leg", "top": 4, "loops": [_rectangle(11.25, 10.25, 0.5, 0.5)]},
        {"id": "front", "kind": "leg", "top": 34.5, "loops": loops},
    ]})
    assert _segments(make_plan_doc(plan, ROOM)) == _normalized([edge for loop in loops for edge in _edges(loop)])
    open_plan = PayloadPlan.model_validate({"parts": [CABINET], "shapes": [
        {"id": "open", "kind": "leg", "top": 40, "loops": [opened]},
    ]})
    assert _segments(make_plan_doc(open_plan, ROOM), "CABINETS") == _normalized(_edges({
        "closed": True, "points": CABINET["points"],
    }))
    shape = _circle(35, 12)
    assert PayloadPlan().shapes == []
    assert PayloadPlanShape.model_validate(shape).model_dump(mode="json") == shape
    for change in ({"id": ""}, {"kind": "accessory"}, {"top": float("nan")},
                   {"loops": []}, {"extra": True},
                   {"loops": [{"closed": True, "points": [[0, 0], [1, 0]]}]}):
        with pytest.raises(ValidationError):
            PayloadPlan.model_validate({"shapes": [{**shape, **change}]})
    with pytest.raises(ValidationError):
        PayloadPlanPart.model_validate({**CABINET, "kind": "leg"})


def test_no_leg_anchor_keeps_payload_and_dxf_bytes_without_legs_layer(monkeypatch):
    monkeypatch.setattr(ezdxf.options, "write_fixed_meta_data_for_testing", True)
    payload = _payload(parts=[DOOR], shapes=[])
    del payload["elevations"][0]["shapes"]
    payload["plan"] = {"parts": [CABINET]}
    model = DrawingPayload.model_validate(payload)
    assert model.model_dump(mode="json", exclude_defaults=True) == payload
    elevation = build_elevation_dxf(model.elevations[0], model.room)
    plan = build_plan_dxf(model.plan, model.room)
    for doc in (_doc(payload), make_plan_doc(model.plan, model.room)):
        assert "LEGS" not in doc.layers and "ACCESSORIES" not in doc.layers
    monkeypatch.delitem(LEG_LAYER_DEFS, "LEGS")
    assert elevation == build_elevation_dxf(model.elevations[0], model.room)
    assert plan == build_plan_dxf(model.plan, model.room)
    explicit = PayloadPlan.model_validate({**payload["plan"], "shapes": []})
    assert plan == build_plan_dxf(explicit, model.room)
