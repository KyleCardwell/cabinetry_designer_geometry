"""Part number payloads and elevation DXF badges (SPEC-50.13)."""

import base64
import copy
import io
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest
from ezdxf import bbox
from ezdxf.enums import TextEntityAlignment
from pydantic import ValidationError

from src.drawing.bundle import draw
from src.drawing.models import PayloadElevation, PayloadPartNumber

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "g1_payload.json").read_text())
BADGE = {"key": "a", "text": "1", "x": 15, "z": 19.25, "width": 6, "height": 4.5, "leader": None}


def _dxf(badges=None, scale=24):
    payload = copy.deepcopy(PAYLOAD)
    payload["elevations"] = payload["elevations"][:1]
    payload["plotScale"] = scale
    if badges is not None:
        payload["elevations"][0]["partNumbers"] = badges
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read("elevation-A.dxf").decode("utf-8")))


def _entities(doc):
    return list(doc.modelspace().query('*[layer=="PART_NUMBERS"]'))


def test_slot_and_centred_text_match_anchor_without_leader():
    entities = _entities(_dxf([BADGE]))
    assert [entity.dxftype() for entity in entities] == ["LWPOLYLINE", "TEXT"]
    slot, text = entities
    assert slot.closed
    assert list(slot.get_points("xyb")) == [
        (14.25, 17, 0), (15.75, 17, 1), (15.75, 21.5, 0), (14.25, 21.5, 1),
    ]
    bounds = bbox.extents([slot])
    assert tuple(bounds.extmin) == pytest.approx((12, 17, 0))
    assert tuple(bounds.extmax) == pytest.approx((18, 21.5, 0))
    assert text.dxf.text == "1"
    assert text.dxf.height == 3
    assert text.dxf.style == "FF_TEXT"
    assert text.get_align_enum() == TextEntityAlignment.MIDDLE_CENTER
    assert tuple(text.dxf.align_point) == (15, 19.25, 0)
    assert all(entity.dxf.color == 256 for entity in entities)


def test_shifted_badge_and_leader_match_anchor():
    badge = {**BADGE, "text": "2", "x": 31.5, "z": 25.25,
             "leader": {"x1": 31.5, "z1": 23, "x2": 31.5, "z2": 19.25}}
    slot, text, leader = _entities(_dxf([badge]))
    assert list(slot.get_points("xyb")) == [
        (30.75, 23, 0), (32.25, 23, 1), (32.25, 27.5, 0), (30.75, 27.5, 1),
    ]
    assert slot.closed
    assert text.dxf.text == "2"
    assert text.dxf.height == 3
    assert text.dxf.style == "FF_TEXT"
    assert text.get_align_enum() == TextEntityAlignment.MIDDLE_CENTER
    assert tuple(text.dxf.align_point) == (31.5, 25.25, 0)
    assert leader.dxftype() == "LINE"
    assert tuple(leader.dxf.start) == (31.5, 23, 0)
    assert tuple(leader.dxf.end) == (31.5, 19.25, 0)
    assert leader.dxf.color == 256


def test_equal_width_and_height_make_circle_anchor():
    circle, text = _entities(_dxf([{**BADGE, "text": "9", "x": 0, "z": 0, "width": 4.5}]))
    assert circle.dxftype() == "CIRCLE"
    assert circle.dxf.radius == 2.25
    bounds = bbox.extents([circle])
    assert tuple(bounds.extmin) == pytest.approx((-2.25, -2.25, 0))
    assert tuple(bounds.extmax) == pytest.approx((2.25, 2.25, 0))
    assert text.dxf.text == "9"


def test_omitted_badges_leave_empty_part_numbers_layer():
    doc = _dxf()
    layer = doc.layers.get("PART_NUMBERS")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (7, "CONTINUOUS", 18)
    assert _entities(doc) == []
    assert PayloadElevation.model_validate(PAYLOAD["elevations"][0]).partNumbers == []


def test_frame_includes_badge_below_fixture():
    doc = _dxf([{**BADGE, "z": -40}])
    assert doc.header["$EXTMIN"][1] <= -40 - 2.25 - 24


def test_multiple_badges_keep_supplied_sizes_and_positions_at_other_plot_scale():
    badges = [BADGE, {**BADGE, "key": "molding", "text": "TK 7", "x": 60, "width": 9.6}]
    entities = _entities(_dxf(badges, scale=48))
    assert [entity.dxftype() for entity in entities] == ["LWPOLYLINE", "TEXT"] * 2
    for badge, slot, text in zip(badges, entities[::2], entities[1::2]):
        bounds = bbox.extents([slot])
        assert bounds.size.x == pytest.approx(badge["width"])
        assert bounds.size.y == pytest.approx(badge["height"])
        assert tuple(text.dxf.align_point) == (badge["x"], badge["z"], 0)
        assert text.dxf.text == badge["text"]
        assert text.dxf.height == 3


def test_badge_payload_rejects_unknown_keys_empty_text_and_nonpositive_sizes():
    invalid = [
        {"unknown": True}, {"text": ""}, {"width": 0}, {"width": -1},
        {"height": 0}, {"height": -1},
        {"leader": {"x1": 0, "z1": 0, "x2": 1, "z2": 1, "unknown": True}},
    ]
    for changes in invalid:
        with pytest.raises(ValidationError):
            PayloadPartNumber.model_validate({**BADGE, **changes})
