"""Pre-squashed corner elevation parts and their references (SPEC-CC5 step e)."""

import base64
import copy
import io
import zipfile

import ezdxf
import pytest
from pydantic import ValidationError

from src.drawing.bundle import draw


FACE = {"id": "corner-return:cc:r", "kind": "face", "runId": "R1",
        "x": 25.1165, "z": 4.125, "width": 11.0043, "height": 30.25,
        "back": 24.125, "front": 24.875, "coversBoxEdges": True}
PAYLOAD = {
    "payloadVersion": 1, "units": "in", "room": {"id": "room", "name": "Euro corner"},
    "elevations": [{
        "key": "B:front", "letter": "B", "wallId": "B", "side": "front",
        "title": "Elevation B", "wallLabel": "Return wall", "length": 72, "height": 96,
        "parts": [
            {"id": "corner-return:cc", "kind": "cabinet", "runId": "R1",
             "x": 0, "z": 4, "width": 36, "height": 30.5,
             "back": 0, "front": 24, "coversBoxEdges": False},
            {"id": "corner-return:cc:panel", "kind": "end_panel", "runId": "R1",
             "x": 36, "z": 4, "width": 0.75, "height": 30.5,
             "back": 0, "front": 24, "coversBoxEdges": False},
            FACE,
        ],
        "doorDetails": [{"partId": FACE["id"], "openings": [
            {"x": 27.1165, "z": 6.125, "width": 7.0043, "height": 26.25},
        ]}],
        # Pull size is unchanged by the squash; only its centre was moved.
        "pulls": [{"partId": FACE["id"], "outlines": [[
            (33, 26), (33.375, 26), (33.375, 30), (33, 30),
        ]]}],
    }],
}


def test_squashed_face_keeps_details_and_pull_inside_and_rejects_unknown_detail_id():
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(PAYLOAD)["zip_base64"])))
    msp = ezdxf.read(io.StringIO(archive.read("elevation-B.dxf").decode("utf-8"))).modelspace()
    expected_bounds = {
        "FACES": (25.1165, 4.125, 36.1208, 34.375),
        "DOOR_DETAILS": (27.1165, 6.125, 34.1208, 32.375),
        "PULLS": (33, 26, 33.375, 30),
    }
    for layer, bounds in expected_bounds.items():
        lines = list(msp.query(f'LINE[layer=="{layer}"]'))
        assert len(lines) == 4
        points = [tuple(point)[:2] for line in lines for point in (line.dxf.start, line.dxf.end)]
        assert (min(x for x, z in points), min(z for x, z in points),
                max(x for x, z in points), max(z for x, z in points)) == pytest.approx(bounds)
        if layer != "FACES":
            assert all(FACE["x"] < x < FACE["x"] + FACE["width"]
                       and FACE["z"] < z < FACE["z"] + FACE["height"] for x, z in points)
    assert list(msp.query('LINE[layer=="CABINETS"]'))
    assert list(msp.query('LINE[layer=="PANELS"]'))

    payload = copy.deepcopy(PAYLOAD)
    payload["elevations"][0]["doorDetails"][0]["partId"] = "cc:r"
    with pytest.raises(ValidationError, match="Door details name unknown part ids: cc:r"):
        draw(payload)
