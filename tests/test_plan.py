"""The plan DXF (SPEC-44)."""

import base64
import copy
import io
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest
from pydantic import ValidationError
from shapely.geometry import Polygon

from src.drawing.bundle import draw

ROOT = Path(__file__).resolve().parent.parent
ELEVATIONS = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())

# Two walls meeting at a mitred corner, a window through the first, a base and an upper in front of it.
PLAN = {"parts": [
    {"id": "A:wall", "kind": "wall", "points": [[0, 0], [120, 0], [124.5, 4.5], [0, 4.5]]},
    {"id": "B:wall", "kind": "wall", "points": [[120, 0], [120, -60], [124.5, -60], [124.5, 4.5]]},
    {"id": "W:void", "kind": "void", "points": [[36, 0], [72, 0], [72, 4.5], [36, 4.5]]},
    {"id": "W:detail", "kind": "opening", "points": [[36, 2.25], [72, 2.25]], "closed": False},
    {"id": "W:casing", "kind": "casing", "points": [[33, 0], [75, 0], [75, -0.75], [33, -0.75]]},
    {"id": "box", "kind": "cabinet", "runId": "R1", "points": [[0, 0], [24, 0], [24, -24], [0, -24]]},
    {"id": "box:r", "kind": "face", "runId": "R1",
     "points": [[0.0625, -24.0625], [23.9375, -24.0625], [23.9375, -24.875], [0.0625, -24.875]]},
    {"id": "up", "kind": "cabinet", "runId": "R2", "dashed": True,
     "points": [[84, 0], [120, 0], [120, -12], [84, -12]]},
]}
PAYLOAD = {**ELEVATIONS, "plan": PLAN}


def _archive(payload):
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))


def _modelspace(payload):
    return ezdxf.read(io.StringIO(_archive(payload).read("plan.dxf").decode("utf-8"))).modelspace()


def _polylines(msp, layer):
    return list(msp.query(f'LWPOLYLINE[layer=="{layer}"]'))


def _area(polyline):
    return Polygon([point[:2] for point in polyline.get_points("xy")]).area


def test_plan_dxf_comes_first_only_when_the_payload_has_a_plan():
    result = draw(PAYLOAD)
    elevations = ["elevation-A.dxf", "elevation-B.dxf", "elevation-C.dxf", "elevation-D.dxf"]
    assert result["files"] == ["plan.dxf", *elevations]
    assert _archive(PAYLOAD).namelist() == ["payload.json", "plan.dxf", *elevations]
    assert json.loads(_archive(PAYLOAD).read("payload.json")) == PAYLOAD
    assert draw(ELEVATIONS)["files"] == elevations


def test_walls_join_at_the_corner_and_the_window_cuts_them():
    msp = _modelspace(PAYLOAD)
    walls = _polylines(msp, "WALLS")
    assert all(polyline.closed for polyline in walls)
    assert sorted(round(_area(polyline), 4) for polyline in walls) == [162, 506.25]
    hatches = list(msp.query("HATCH"))
    # Solid, in the layer's colour (SPEC-44.1).
    assert [(hatch.dxf.layer, hatch.dxf.solid_fill, hatch.dxf.color) for hatch in hatches] == [
        ("SECTIONS", 1, 256), ("SECTIONS", 1, 256),
    ]
    assert sorted(round(Polygon([v[:2] for v in hatch.paths.paths[0].vertices]).area, 4) for hatch in hatches) == [
        162, 506.25,
    ]


def test_each_part_is_an_outline_on_its_layer_uppers_dashed():
    msp = _modelspace(PAYLOAD)
    shapes = [
        (polyline.dxf.layer, polyline.closed, polyline.dxf.linetype, [tuple(p) for p in polyline.get_points("xy")])
        for polyline in msp.query("LWPOLYLINE")
        if polyline.dxf.layer != "WALLS"
    ]
    assert shapes == [
        ("OPENINGS", False, "BYLAYER", [(36, 2.25), (72, 2.25)]),
        ("OPENINGS", True, "BYLAYER", [(33, 0), (75, 0), (75, -0.75), (33, -0.75)]),
        ("CABINETS", True, "BYLAYER", [(0, 0), (24, 0), (24, -24), (0, -24)]),
        ("FACES", True, "BYLAYER", [(0.0625, -24.0625), (23.9375, -24.0625), (23.9375, -24.875), (0.0625, -24.875)]),
        ("CABINETS", True, "DASHED", [(84, 0), (120, 0), (120, -12), (84, -12)]),
    ]
    assert [(t.dxf.text, tuple(t.dxf.insert)[:2], t.dxf.height) for t in msp.query("TEXT")] == [
        ("PLAN", (0, -72), 4), ("G1 Euro kitchen", (0, -78), 3),
    ]


def test_rejects_an_unknown_plan_kind_or_a_single_point():
    for change in ({"kind": "stair"}, {"points": [[0, 0]]}):
        payload = copy.deepcopy(PAYLOAD)
        payload["plan"]["parts"][5].update(change)
        with pytest.raises(ValidationError):
            draw(payload)
