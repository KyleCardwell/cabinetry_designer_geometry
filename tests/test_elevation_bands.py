"""Bands, detail lines and the countertop/molding layers (SPEC-42)."""

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
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "g6_bands_payload.json").read_text())


def _archive(payload):
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))


def _modelspace(payload):
    dxf = _archive(payload).read("elevation-A.dxf").decode("utf-8")
    return ezdxf.read(io.StringIO(dxf)).modelspace()


def _lines(msp, layer):
    return list(msp.query(f'LINE[layer=="{layer}"]'))


def _length(lines):
    return sum(line.dxf.start.distance(line.dxf.end) for line in lines)


def test_bands_draw_on_countertops_and_moldings():
    msp = _modelspace(PAYLOAD)
    assert len(_lines(msp, "COUNTERTOPS")) == 4
    assert _length(_lines(msp, "COUNTERTOPS")) == pytest.approx(206.5)
    assert len(_lines(msp, "MOLDINGS")) == 15  # toe kick 4, bottom cap 4, top mold 3, crown 4
    assert _length(_lines(msp, "MOLDINGS")) == pytest.approx(726.75)
    assert _lines(msp, "HIDDEN") == []  # the top mold behind the crown is left out, not dashed


def test_chip_lines_draw_on_their_parts_layer():
    msp = _modelspace(PAYLOAD)
    for layer, span in (("FILLERS", [0, 2.75]), ("PANELS", [100.25, 101])):
        chips = [
            line for line in _lines(msp, layer)
            if line.dxf.start.y == pytest.approx(54.125) and line.dxf.end.y == pytest.approx(54.125)
        ]
        assert len(chips) == 1
        assert sorted([chips[0].dxf.start.x, chips[0].dxf.end.x]) == pytest.approx(span)


def test_profile_ids_pass_through_and_bad_parts_are_rejected():
    payload = copy.deepcopy(PAYLOAD)
    payload["elevations"][0]["parts"][-1]["profileId"] = "crown-4-1-2"
    assert _length(_lines(_modelspace(payload), "MOLDINGS")) == pytest.approx(726.75)
    stored = json.loads(_archive(payload).read("payload.json"))
    assert stored["elevations"][0]["parts"][-1]["profileId"] == "crown-4-1-2"
    for patch in ({"kind": "trim"}, {"lines": [{"x1": 0, "z1": 0, "x2": 1, "z2": 0, "layer": "X"}]}):
        bad = copy.deepcopy(PAYLOAD)
        bad["elevations"][0]["parts"][0].update(patch)
        with pytest.raises(ValidationError):
            draw(bad)
