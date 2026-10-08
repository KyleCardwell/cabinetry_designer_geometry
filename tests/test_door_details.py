"""Door details and style tags in the elevation DXF (SPEC-46.4)."""

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

# Faces as the designer sends them (SPEC-46.4): G1's 24" base door, the left leaf of its tall, G3's top drawer.
DOOR = {"id": "door", "kind": "face", "x": 30.0625, "z": 4.125, "width": 23.875, "height": 30.125,
        "back": 24.0625, "front": 24.875, "coversBoxEdges": True}
LEAF = {"id": "leaf", "kind": "face", "x": 0.8125, "z": 4.125, "width": 14.125, "height": 85.75,
        "back": 25.0625, "front": 25.875, "coversBoxEdges": True}
DRAWER = {"id": "drawer", "kind": "face", "x": 1.5625, "z": 28.375, "width": 19.375, "height": 5.875,
          "back": 21.0625, "front": 21.875, "coversBoxEdges": True}
# A panel 1" in front of the door, across its top: z 26 to 36.
SHADE = {"id": "shade", "kind": "panel", "x": 30, "z": 26, "width": 30, "height": 10,
         "back": 24.875, "front": 25.875, "coversBoxEdges": False}


def _box(x, z, width, height):
    return {"x": x, "z": z, "width": width, "height": height}


DOOR_OPENING = _box(33.0625, 7.125, 17.875, 24.125)


def _payload(parts, details, plot_scale=None):
    payload = copy.deepcopy(PAYLOAD)
    payload["elevations"][0]["parts"] = copy.deepcopy(parts)
    payload["elevations"][0]["doorDetails"] = copy.deepcopy(details)
    if plot_scale is not None:
        payload["plotScale"] = plot_scale
    return payload


def _msp(payload):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read("elevation-A.dxf").decode("utf-8"))).modelspace()


def _lines(msp, layer):
    return list(msp.query(f'LINE[layer=="{layer}"]'))


def _length(lines):
    return sum(line.dxf.start.distance(line.dxf.end) for line in lines)


def test_each_opening_draws_on_door_details_inside_its_face():
    msp = _msp(_payload([DOOR], [{"partId": "door", "openings": [DOOR_OPENING]}]))
    details = _lines(msp, "DOOR_DETAILS")
    assert len(details) == 4
    assert _length(details) == pytest.approx(84)
    xs = [x for line in details for x in (line.dxf.start.x, line.dxf.end.x)]
    zs = [z for line in details for z in (line.dxf.start.y, line.dxf.end.y)]
    assert (min(xs), min(zs), max(xs), max(zs)) == pytest.approx((33.0625, 7.125, 50.9375, 31.25))
    assert len(_lines(msp, "FACES")) == 4
    assert _length(_lines(msp, "FACES")) == pytest.approx(108)
    assert _lines(_msp(_payload([DOOR], [])), "DOOR_DETAILS") == []


def test_mid_rails_come_as_separate_openings():
    msp = _msp(_payload([LEAF], [{"partId": "leaf", "openings": [
        _box(3.8125, 7.125, 8.125, 37.5), _box(3.8125, 47.625, 8.125, 39.25),
    ]}]))
    assert len(_lines(msp, "DOOR_DETAILS")) == 8
    assert _length(_lines(msp, "DOOR_DETAILS")) == pytest.approx(186)


def test_a_nearer_part_hides_door_details_and_they_are_never_dashed():
    msp = _msp(_payload([DOOR, SHADE], [{"partId": "door", "openings": [DOOR_OPENING]}]))
    details = _lines(msp, "DOOR_DETAILS")
    assert len(details) == 3  # the bottom, and each side up to the panel; the top is behind it
    assert _length(details) == pytest.approx(55.625)
    hidden = _lines(msp, "HIDDEN")  # only the door's own outline behind the panel
    assert len(hidden) == 3
    assert _length(hidden) == pytest.approx(40.375)


def test_door_details_round_trip_and_must_name_a_part_in_their_elevation():
    payload = _payload([DOOR], [{"partId": "door", "openings": [DOOR_OPENING], "tag": "A"}])
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    assert json.loads(archive.read("payload.json")) == payload
    for detail in (
        {"partId": "nope", "openings": [DOOR_OPENING]},
        {"partId": "door", "openings": [_box(33, 7, 0, 24)]},
        {"partId": "door", "tag": ""},
        {"partId": "door", "color": "red"},
    ):
        with pytest.raises(ValidationError):
            draw(_payload([DOOR], [detail]))
