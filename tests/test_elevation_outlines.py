"""True part outlines in elevations (SPEC-50.2, step 469)."""

import base64
import io
import json
import zipfile

import ezdxf
import pytest
from pydantic import ValidationError
from shapely.geometry import Polygon

from src.drawing.bundle import draw
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
        Polygon([vertex[:2] for vertex in hatch.paths.paths[0].vertices]).area
        for hatch in msp.query('HATCH[layer=="SECTIONS"]')
    )


def test_crown_outline_has_its_true_perimeter_and_round_trips():
    part = _part(holes=[{"x": 0.5, "z": 0.25, "width": 0.5, "height": 0.5}])
    msp = _modelspace(part)
    assert len(msp.query('LINE[layer=="MOLDINGS"]')) == 4
    assert _length(msp, "MOLDINGS") == pytest.approx(12.2426, abs=1e-4)
    with _archive(part) as archive:
        assert json.loads(archive.read("payload.json"))["elevations"][0]["parts"][0] == part


def test_section_outline_hatches_the_polygon_and_ignores_holes():
    msp = _modelspace(_part(
        kind="section", holes=[{"x": 0.5, "z": 0.25, "width": 0.5, "height": 0.5}],
    ))
    assert _hatch_area(msp) == pytest.approx(7.5)
    assert _length(msp, "SECTIONS") == pytest.approx(12.2426, abs=1e-4)


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
