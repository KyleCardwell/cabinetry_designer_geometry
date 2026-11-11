"""Hand-built corner cabinet plan payloads (SPEC-CC5 step e)."""

import base64
from collections import Counter
import io
from math import sqrt
import zipfile

import ezdxf
import pytest

from src.drawing.bundle import draw


WALL = {"id": "A:wall", "kind": "wall",
        "points": [(0, -4.5), (40, -4.5), (40, 0), (0, 0)]}
L_BOX = [(0, 0), (36, 0), (36, 24), (24, 24), (24, 36), (0, 36)]
DIAGONAL_BOX = [(0, 0), (36, 0), (36, 24), (24, 36), (0, 36)]


def _part(part_id, kind, points, top=34.5):
    return {"id": part_id, "kind": kind, "runId": "R1", "points": points, "top": top}


def _modelspace(parts):
    payload = {
        "payloadVersion": 1, "units": "in",
        "room": {"id": "room", "name": "Euro corner"}, "elevations": [],
        "plan": {"parts": [WALL, *parts]},
    }
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read("plan.dxf").decode("utf-8"))).modelspace()


def _edges(points):
    return list(zip(points, points[1:] + points[:1]))


def _normalized(segments):
    # Ignore traversal direction, but retain duplicate edges and tolerate DXF float noise.
    return Counter(tuple(sorted(tuple(round(v, 6) for v in p) for p in segment))
                   for segment in segments)


def _assert_lines(msp, expected):
    lines = list(msp.query("LINE"))
    assert Counter(line.dxf.layer for line in lines) == Counter(
        {layer: len(segments) for layer, segments in expected.items()}
    )
    for layer, segments in expected.items():
        actual = [(tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2])
                  for line in lines if line.dxf.layer == layer]
        assert _normalized(actual) == _normalized(segments)
    assert {line.dxf.linetype for line in lines} == {"BYLAYER"}
    # No fallback rectangular outlines, duplicate polylines or hidden geometry.
    assert {polyline.dxf.layer for polyline in msp.query("LWPOLYLINE")} == {"WALLS"}
    assert not list(msp.query('LINE[layer=="HIDDEN"]'))


def test_l_plan_has_six_box_edges_both_leg_faces_and_return_panel():
    leg_a = [(24.9375, 24.125), (35.9375, 24.125),
             (35.9375, 24.875), (24.9375, 24.875)]
    leg_b = [(24.125, 24.9375), (24.875, 24.9375),
             (24.875, 35.9375), (24.125, 35.9375)]
    panel = [(0, 36), (24, 36), (24, 36.75), (0, 36.75)]
    msp = _modelspace([
        _part("cc", "cabinet", L_BOX),
        _part("cc:r", "face", leg_a), _part("cc:B:r", "face", leg_b),
        _part("cc:return", "end_panel", panel),
    ])
    _assert_lines(msp, {
        "CABINETS": _edges(L_BOX), "FACES": _edges(leg_a) + _edges(leg_b),
        "PANELS": _edges(panel),
    })


def test_five_sided_plan_has_diagonal_box_edge_and_three_quarter_inch_door_ends():
    # Front plane is 7/8" out from the box diagonal; thickness goes back 3/4".
    front, back = 0.875 / sqrt(2), 0.125 / sqrt(2)
    door = [(36 + front, 24 + front), (24 + front, 36 + front),
            (24 + back, 36 + back), (36 + back, 24 + back)]
    msp = _modelspace([
        _part("cc", "cabinet", DIAGONAL_BOX), _part("cc:r", "face", door),
    ])
    _assert_lines(msp, {"CABINETS": _edges(DIAGONAL_BOX), "FACES": _edges(door)})
    lines = list(msp.query('LINE[layer=="FACES"]'))
    lengths = sorted(line.dxf.start.distance(line.dxf.end) for line in lines)
    assert lengths == pytest.approx([0.75, 0.75, 12 * sqrt(2), 12 * sqrt(2)])
    for line in lines:
        dx, dy = line.dxf.end.x - line.dxf.start.x, line.dxf.end.y - line.dxf.start.y
        assert abs(dx) == pytest.approx(abs(dy))


def test_higher_face_hides_only_the_covered_middle_of_the_diagonal_box_edge():
    # A 3/4" thick slanted face crosses the box edge between (32,28) and (28,32).
    half_thickness = 0.375 / sqrt(2)
    cover = [(32 + half_thickness, 28 + half_thickness),
             (28 + half_thickness, 32 + half_thickness),
             (28 - half_thickness, 32 - half_thickness),
             (32 - half_thickness, 28 - half_thickness)]
    for top in (34.5, 35.5):
        msp = _modelspace([
            _part("cc", "cabinet", DIAGONAL_BOX), _part("cc:r", "face", cover, top),
        ])
        box_edges = _edges(DIAGONAL_BOX)
        if top > 34.5:
            box_edges[2:3] = [((36, 24), (32, 28)), ((28, 32), (24, 36))]
        _assert_lines(msp, {"CABINETS": box_edges, "FACES": _edges(cover)})
