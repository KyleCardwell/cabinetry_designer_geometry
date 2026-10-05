"""Corner returns in section and neighbour profiles (SPEC-42.2)."""

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
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "corners_payload.json").read_text())


def _archive(payload):
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))


def _modelspace(payload):
    dxf = _archive(payload).read("elevation-B.dxf").decode("utf-8")
    return ezdxf.read(io.StringIO(dxf)).modelspace()


def _lines(msp, layer):
    return list(msp.query(f'LINE[layer=="{layer}"]'))


def _length(lines):
    return sum(line.dxf.start.distance(line.dxf.end) for line in lines)


def _hatch_areas(msp):
    return [
        Polygon([vertex[:2] for vertex in hatch.paths.paths[0].vertices]).area
        for hatch in msp.query('HATCH[layer=="SECTIONS"]')
    ]


def test_sections_are_outlined_and_hatched_on_sections():
    msp = _modelspace(PAYLOAD)
    assert len(_lines(msp, "SECTIONS")) == 8
    assert _length(_lines(msp, "SECTIONS")) == pytest.approx(171.75)
    hatches = list(msp.query("HATCH"))
    assert [(hatch.dxf.layer, hatch.dxf.pattern_name, hatch.dxf.pattern_scale) for hatch in hatches] == [
        ("SECTIONS", "ANSI31", 24), ("SECTIONS", "ANSI31", 24),
    ]
    assert _hatch_areas(msp) == pytest.approx([732, 26.6875])


def test_a_section_hides_the_blind_box_behind_it_and_its_bands_hide_nothing():
    msp = _modelspace(PAYLOAD)
    hidden = _lines(msp, "HIDDEN")
    assert len(hidden) == 1  # the blind box's end, in the corner behind the return
    assert [hidden[0].dxf.start.x, hidden[0].dxf.end.x] == pytest.approx([9.1875, 9.1875])
    assert sorted([hidden[0].dxf.start.y, hidden[0].dxf.end.y]) == pytest.approx([4, 34.5])
    # Both countertops whole: the return's countertop is an outline (opaque: false).
    assert _length(_lines(msp, "COUNTERTOPS")) == pytest.approx(247.5)
    # The blind box's visible edges plus the profile's 24 x 30 1/2 box past the wall end.
    assert _length(_lines(msp, "CABINETS")) == pytest.approx(62.8125 + 109)
    assert _length(_lines(msp, "MOLDINGS")) == pytest.approx(50)


def test_only_the_visible_part_of_a_section_is_hatched_and_kinds_are_checked():
    covered = copy.deepcopy(PAYLOAD)
    covered["elevations"][0]["parts"].append({
        "id": "post", "kind": "panel", "x": 20, "z": 0, "width": 10, "height": 40,
        "back": 0, "front": 200, "coversBoxEdges": False,
    })
    assert _hatch_areas(_modelspace(covered)) == pytest.approx([20 * 30.5])  # the faces are covered
    stored = json.loads(_archive(PAYLOAD).read("payload.json"))
    assert stored == PAYLOAD
    bad = copy.deepcopy(PAYLOAD)
    bad["elevations"][0]["parts"][2]["kind"] = "return"
    with pytest.raises(ValidationError):
        draw(bad)
