"""True part outlines in elevations (SPEC-50.2, step 469)."""

import base64
import io
import json
from math import acos, degrees, hypot, pi
import zipfile

import ezdxf
import pytest
from pydantic import ValidationError
from shapely.geometry import Polygon

from src.drawing.bundle import draw
from src.drawing.arcs import flatten_outline
from src.drawing.models import PayloadPart


OUTLINE = [[0, 0], [3, 0], [3, 1], [0, 4]]


def _part(**patch):
    return {
        "id": "outline", "kind": "crown", "x": 0, "z": 0, "width": 3, "height": 4,
        "back": 0, "front": 2, "coversBoxEdges": False, "outline": OUTLINE,
        **patch,
    }


def _archive(*parts):
    payload = {
        "payloadVersion": 1, "units": "in", "room": {"id": "room", "name": "Room"},
        "elevations": [{
            "key": "wall:front", "letter": "A", "wallId": "wall", "side": "front",
            "title": "Elevation A", "wallLabel": "Wall A", "length": 10, "height": 10,
            "parts": list(parts),
        }],
    }
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))


def _modelspace(*parts):
    with _archive(*parts) as archive:
        return ezdxf.read(io.StringIO(archive.read("elevation-A.dxf").decode())).modelspace()


def _length(msp, layer):
    return sum(line.dxf.start.distance(line.dxf.end) for line in msp.query(f'LINE[layer=="{layer}"]'))


def _hatch_area(msp):
    return sum(
        Polygon(
            [vertex[:2] for vertex in hatch.paths.paths[0].vertices],
            [[vertex[:2] for vertex in path.vertices] for path in hatch.paths.paths[1:]],
        ).area
        for hatch in msp.query('HATCH[layer=="SECTIONS"]')
    )


def test_crown_outline_has_its_true_perimeter_and_round_trips():
    for holes in ([], [{"x": 0.5, "z": 0.25, "width": 0.5, "height": 0.5}]):
        part = _part()
        if holes:
            part["holes"] = holes
        msp = _modelspace(part)
        assert len(msp.query('LINE[layer=="MOLDINGS"]')) == 4 + 4 * len(holes)
        assert _length(msp, "MOLDINGS") == pytest.approx(12.2426 + 2 * len(holes), abs=1e-4)
        with _archive(part) as archive:
            assert json.loads(archive.read("payload.json"))["elevations"][0]["parts"][0] == part


def test_section_outline_hatches_the_polygon_with_its_holes():
    msp = _modelspace(_part(
        kind="section", holes=[
            {"x": 0.5, "z": 0.25, "width": 0.5, "height": 0.5},
            {"x": 1.5, "z": 0.25, "width": 0.5, "height": 0.5},
        ],
    ))
    assert _hatch_area(msp) == pytest.approx(7)
    assert _length(msp, "SECTIONS") == pytest.approx(16.2426, abs=1e-4)


@pytest.mark.parametrize("holes, area", [
    ([], 96),
    ([{"x": 1, "z": 1, "width": 2, "height": 2}], 92),
])
def test_notched_outline_keeps_its_area_and_draws_hole_edges(holes, area):
    outline = [[0, 0], [10, 0], [10, 10], [6, 10], [6, 8], [4, 8], [4, 10], [0, 10]]
    msp = _modelspace(_part(
        kind="section", width=10, height=10, outline=outline, holes=holes,
    ))
    assert _hatch_area(msp) == pytest.approx(area)
    expected_rings = [outline] + ([[[1, 1], [3, 1], [3, 3], [1, 3]]] if holes else [])
    expected_edges = {
        frozenset((tuple(start), tuple(end)))
        for ring in expected_rings
        for start, end in zip(ring, ring[1:] + ring[:1])
    }
    lines = msp.query('LINE[layer=="SECTIONS"]')
    assert len(lines) == len(expected_edges)
    assert {
        frozenset((tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2]))
        for line in lines
    } == expected_edges


@pytest.mark.parametrize("outline", [
    [[0, 0], [3, 0], [3.5, 1], [0, 4]],
    [[0, 0], [3, 0]],
    [[0, 0], [1, 1], [2, 2]],
])
def test_invalid_outlines_are_validation_errors(outline):
    with pytest.raises(ValidationError):
        _modelspace(_part(outline=outline))


def test_outline_bounds_allow_only_the_specified_tolerance_at_each_side():
    for side in ("left", "right", "bottom", "top"):
        for delta, accepted in ((0.5e-6, True), (2e-6, False)):
            left = 10 - delta if side == "left" else 10
            right = 13 + delta if side == "right" else 13
            bottom = 20 - delta if side == "bottom" else 20
            top = 24 + delta if side == "top" else 24
            part = _part(x=10, z=20, outline=[
                [left, bottom], [right, bottom], [right, top], [left, top], [left, bottom],
            ])
            if accepted:
                assert PayloadPart.model_validate(part).outline is not None
            else:
                with pytest.raises(ValidationError):
                    PayloadPart.model_validate(part)


def test_outline_opacity_clips_hidden_lines_and_section_hatching_to_the_true_shape():
    rear = _part(id="rear", kind="section", front=1, outline=None,
                 lines=[{"x1": 0, "z1": 2, "x2": 3, "z2": 2}])
    # The diagonal meets the detail line at x=2. Coincident boundary edges are not dashed.
    for opaque, visible, hidden, area in ((True, 7, 2, 4.5), (False, 17, 0, 12)):
        msp = _modelspace(rear, _part(opaque=opaque))
        assert _length(msp, "SECTIONS") == pytest.approx(visible)
        assert _length(msp, "HIDDEN") == pytest.approx(hidden)
        assert _hatch_area(msp) == pytest.approx(area)


ARC_OUTLINE = [[0, 0, 0], [4, 0, 0.414214], [0, 4, 0]]


def _arc_part(**patch):
    return _part(**{"width": 4, "outline": ARC_OUTLINE, **patch})


def _assert_arc(arc, start, end):
    # Six-place bulges introduce a few millionths of an inch of circle error.
    assert tuple(arc.dxf.center)[:2] == pytest.approx((0, 0), abs=1e-5)
    assert arc.dxf.radius == pytest.approx(4, abs=1e-5)
    for actual, expected in ((arc.dxf.start_angle, start), (arc.dxf.end_angle, end)):
        assert (actual - expected + 180) % 360 - 180 == pytest.approx(0, abs=1e-4)


def test_bulged_outline_writes_true_arc_and_preserves_straight_edges():
    # Anchor 1, then reversed walking direction and a mirrored negative bulge.
    for outline, bounds, angles in (
        (ARC_OUTLINE, {}, (0, 90)),
        ([[0, 0], [0, 4, -0.414214], [4, 0]], {}, (0, 90)),
        ([[0, 0], [-4, 0, -0.414214], [0, 4]], {"x": -4}, (90, 180)),
        ([[0, 0], [0, -4, 0.414214], [4, 0]], {"z": -4}, (270, 0)),
        # The arc may also be the implicitly closing segment.
        ([[0, 4], [0, 0], [4, 0, 0.414214]], {}, (0, 90)),
    ):
        part = _arc_part(**bounds)
        part["outline"] = outline
        msp = _modelspace(part)
        lines = msp.query('LINE[layer=="MOLDINGS"]')
        assert len(lines) == 2
        assert [line.dxf.start.distance(line.dxf.end) for line in lines] == pytest.approx([4, 4])
        arcs = msp.query('ARC[layer=="MOLDINGS"]')
        assert len(arcs) == 1
        _assert_arc(arcs[0], *angles)
        assert not msp.query('ARC[layer=="HIDDEN"]')
    with _archive(_arc_part()) as archive:
        assert json.loads(archive.read("payload.json"))["elevations"][0]["parts"][0] == _arc_part()
    points, arcs = flatten_outline([tuple(point) for point in ARC_OUTLINE])
    arc = arcs[0]
    for start, end in zip(points[1:], points[2:]):
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        assert abs(hypot(mid[0] - arc.center[0], mid[1] - arc.center[1]) - arc.radius) <= 0.001


def test_crown_arc_hidden_by_cabinet_is_rejoined_and_hidden_piece_dropped():
    msp = _modelspace(_arc_part(), _part(
        id="cover", kind="cabinet", width=2, height=5, front=3, outline=None,
    ))
    arcs = msp.query('ARC[layer=="MOLDINGS"]')
    assert len(arcs) == 1
    _assert_arc(arcs[0], 0, 60)
    assert not msp.query('ARC[layer=="HIDDEN"]')


def test_section_arc_retains_hidden_stretches_and_hatches_flattened_polygon():
    section = _arc_part(kind="section")
    alone = _modelspace(section)
    assert _hatch_area(alone) == pytest.approx(4 * pi, abs=1e-4)
    # A strip creates two visible stretches, separated by one dashed stretch.
    msp = _modelspace(section, _part(
        id="cover", kind="cabinet", x=1, width=1, height=5, front=3, outline=None,
    ))
    visible = sorted(msp.query('ARC[layer=="SECTIONS"]'), key=lambda arc: arc.dxf.end_angle)
    hidden = msp.query('ARC[layer=="HIDDEN"]')
    assert len(visible) == 2
    assert len(hidden) == 1
    split = degrees(acos(0.25))
    _assert_arc(visible[0], 0, 60)
    _assert_arc(visible[1], split, 90)
    _assert_arc(hidden[0], 60, split)
    assert len(msp.query('LINE[layer=="SECTIONS"]')) == 3
    assert _hatch_area(msp) < _hatch_area(alone)
    # A straight detail chord with both ends on the circle must stay a LINE.
    msp = _modelspace(_arc_part(lines=[{"x1": 4, "z1": 0, "x2": 0, "z2": 4}]))
    assert len(msp.query('LINE[layer=="MOLDINGS"]')) == 3
    assert len(msp.query('ARC[layer=="MOLDINGS"]')) == 1


def test_bulge_validation_checks_limit_rounding_and_flattened_bounds():
    for bulge in (1.5, -1.5, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            PayloadPart.model_validate(_arc_part(outline=[[0, 0], [4, 0, bulge], [0, 4]]))
    # The vertices fit the rectangle, but this semicircle bows below it.
    with pytest.raises(ValidationError, match="bounds"):
        PayloadPart.model_validate(_arc_part(outline=[[0, 0, 1], [4, 0], [0, 4]]))
    for bulge in (-1, 1):
        assert PayloadPart.model_validate(_arc_part(
            z=-2, height=6, outline=[[0, 0, bulge], [4, 0], [0, 4]],
        )).outline is not None
    part = PayloadPart.model_validate(_arc_part(outline=[[0, 0], [4, 0, 0.414213562], [0, 4]]))
    assert part.outline[1][2] == 0.414214
    with pytest.raises(ValidationError, match="distinct endpoints"):
        PayloadPart.model_validate(_arc_part(outline=[[0, 0, 1], [0, 0], [4, 4]]))
