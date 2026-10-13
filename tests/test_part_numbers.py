"""Part number payloads and elevation DXF text and leaders (SPEC-50.14)."""

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


def test_centred_text_only_matches_anchor_without_leader():
    doc = _dxf([BADGE])
    entities = _entities(doc)
    assert [entity.dxftype() for entity in entities] == ["TEXT"]
    text, = entities
    assert text.dxf.text == "1"
    assert text.dxf.height == 3
    assert text.dxf.style == "FF_TEXT"
    assert text.get_align_enum() == TextEntityAlignment.MIDDLE_CENTER
    assert tuple(text.dxf.align_point) == (15, 19.25, 0)
    assert all(entity.dxf.color == 256 for entity in entities)
    layer = doc.layers.get("PART_NUMBERS")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (1, "CONTINUOUS", 18)


def test_shifted_badge_and_leader_match_anchor():
    badge = {**BADGE, "text": "2", "x": 31.5, "z": 25.25,
             "leader": {"x1": 31.5, "z1": 23, "x2": 31.5, "z2": 19.25}}
    entities = _entities(_dxf([badge]))
    assert [entity.dxftype() for entity in entities] == ["TEXT", "LINE"]
    text, leader = entities
    assert text.dxf.text == "2"
    assert text.dxf.height == 3
    assert text.dxf.style == "FF_TEXT"
    assert text.get_align_enum() == TextEntityAlignment.MIDDLE_CENTER
    assert tuple(text.dxf.align_point) == (31.5, 25.25, 0)
    assert leader.dxftype() == "LINE"
    assert tuple(leader.dxf.start) == (31.5, 23, 0)
    assert tuple(leader.dxf.end) == (31.5, 19.25, 0)
    assert all(entity.dxf.color == 256 for entity in entities)


def test_molding_text_only_matches_anchor():
    badge = {**BADGE, "text": "TK 7", "z": 2, "width": 9.6}
    del badge["leader"]
    entities = _entities(_dxf([badge]))
    assert [entity.dxftype() for entity in entities] == ["TEXT"]
    text, = entities
    assert text.dxf.text == "TK 7"
    assert text.dxf.height == 3
    assert text.dxf.style == "FF_TEXT"
    assert text.get_align_enum() == TextEntityAlignment.MIDDLE_CENTER
    assert tuple(text.dxf.align_point) == (15, 2, 0)
    assert text.dxf.color == 256


def test_omitted_badges_leave_empty_part_numbers_layer():
    doc = _dxf()
    layer = doc.layers.get("PART_NUMBERS")
    assert (layer.dxf.color, layer.dxf.linetype, layer.dxf.lineweight) == (1, "CONTINUOUS", 18)
    assert _entities(doc) == []
    assert PayloadElevation.model_validate(PAYLOAD["elevations"][0]).partNumbers == []


def test_frame_includes_badge_below_fixture():
    doc = _dxf([{**BADGE, "z": -40}])
    bounds = bbox.extents(_entities(doc))
    assert doc.header["$EXTMIN"][1] == pytest.approx(bounds.extmin.y - 12)


def test_multiple_badges_keep_supplied_sizes_and_positions_at_other_plot_scale():
    badges = [BADGE, {**BADGE, "key": "round", "text": "9", "x": 30, "width": 4.5},
              {**BADGE, "key": "molding", "text": "TK 7", "x": 60, "width": 9.6}]
    entities = _entities(_dxf(badges, scale=48))
    assert [entity.dxftype() for entity in entities] == ["TEXT"] * 3
    for badge, text in zip(badges, entities):
        assert tuple(text.dxf.align_point) == (badge["x"], badge["z"], 0)
        assert text.dxf.text == badge["text"]
        assert text.dxf.height == 3
        assert text.dxf.style == "FF_TEXT"
        assert text.get_align_enum() == TextEntityAlignment.MIDDLE_CENTER
        assert text.dxf.color == 256


def test_badge_payload_rejects_unknown_keys_empty_text_and_nonpositive_sizes():
    invalid = [
        {"unknown": True}, {"text": ""}, {"width": 0}, {"width": -1},
        {"height": 0}, {"height": -1},
        {"leader": {"x1": 0, "z1": 0, "x2": 1, "z2": 1, "unknown": True}},
    ]
    for changes in invalid:
        with pytest.raises(ValidationError):
            PayloadPartNumber.model_validate({**BADGE, **changes})
