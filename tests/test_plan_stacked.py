"""Plan parts that stack (SPEC-44.1)."""

import base64
import io
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest

from src.drawing.bundle import draw

ROOT = Path(__file__).resolve().parent.parent
ELEVATIONS = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())

# A 36" base, 24" deep, with a 12" deep upper over its back half.
STACKED = {"parts": [
    {"id": "base", "kind": "cabinet", "runId": "R1", "top": 34.5,
     "points": [[0, 0], [36, 0], [36, -24], [0, -24]]},
    {"id": "upper", "kind": "cabinet", "runId": "R2", "top": 90,
     "points": [[0, 0], [36, 0], [36, -12], [0, -12]]},
    {"id": "door", "kind": "casing", "points": [[40, 0], [80, 0], [80, -0.75], [40, -0.75]]},
]}


def _dxf(payload, name):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read(name).decode("utf-8")))


def test_a_higher_part_cuts_the_lines_under_it_and_nothing_is_dashed():
    msp = _dxf({**ELEVATIONS, "plan": STACKED}, "plan.dxf").modelspace()
    lines = list(msp.query('LINE[layer=="CABINETS"]'))
    # The upper whole (96"), the base's front and the ends of its sides past the upper (36 + 12 + 12).
    assert sum(line.dxf.start.distance(line.dxf.end) for line in lines) == pytest.approx(156)
    assert {line.dxf.linetype for line in lines} == {"BYLAYER"}
    assert not list(msp.query('LWPOLYLINE[layer=="CABINETS"]'))
    # A part with no top is drawn whole, over everything, as before.
    assert len(list(msp.query('LWPOLYLINE[layer=="OPENINGS"]'))) == 1
