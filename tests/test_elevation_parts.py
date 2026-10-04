"""Elevation parts through hidden-line removal onto layers (SPEC-41)."""

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
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "g2_tall_payload.json").read_text())


def _modelspace(payload):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read("elevation-A.dxf").decode("utf-8"))).modelspace()


def _lines(msp, layer):
    return list(msp.query(f'LINE[layer=="{layer}"]'))


def _length(lines):
    return sum(line.dxf.start.distance(line.dxf.end) for line in lines)


def test_each_kind_draws_its_visible_lines_on_its_layer():
    msp = _modelspace(PAYLOAD)
    assert len(_lines(msp, "FRAMES")) == 12  # outside rectangle + two openings
    assert _length(_lines(msp, "FRAMES")) == pytest.approx(478)
    assert len(_lines(msp, "FACES")) == 16
    assert _length(_lines(msp, "FACES")) == pytest.approx(414)
    assert _lines(msp, "CABINETS") == []  # behind their frame: left out, not dashed
    assert _lines(msp, "PANELS") == []


def test_end_panels_mitered_behind_the_frame_are_dashed():
    msp = _modelspace(PAYLOAD)
    hidden = _lines(msp, "HIDDEN")
    assert len(hidden) == 2
    assert sorted(line.dxf.start.x for line in hidden) == pytest.approx([50.75, 75.75])
    assert [line.dxf.start.distance(line.dxf.end) for line in hidden] == pytest.approx([86, 86])
    assert msp.doc.layers.get("HIDDEN").dxf.linetype == "DASHED"


def test_rejects_unknown_part_kinds_and_empty_parts():
    for patch in ({"kind": "door"}, {"width": 0}):
        payload = copy.deepcopy(PAYLOAD)
        payload["elevations"][0]["parts"][0].update(patch)
        with pytest.raises(ValidationError):
            draw(payload)
