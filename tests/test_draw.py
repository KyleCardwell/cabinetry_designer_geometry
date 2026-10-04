"""Tests for the drawing payload v1 and the draw command (SPEC-40)."""

import base64
import copy
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import ezdxf
import pytest
from ezdxf import units
from pydantic import ValidationError

from src.drawing.bundle import draw

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())


def _zip(result):
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"])))


def _dxf(archive, name):
    return ezdxf.read(io.StringIO(archive.read(name).decode("utf-8")))


def test_one_dxf_per_elevation_in_letter_order():
    result = draw(PAYLOAD)
    names = ["elevation-A.dxf", "elevation-B.dxf", "elevation-C.dxf", "elevation-D.dxf"]
    assert result["payloadVersion"] == 1
    assert result["files"] == names
    assert _zip(result).namelist() == ["payload.json", *names]


def test_elevation_dxf_draws_the_wall_face_and_its_title():
    archive = _zip(draw(PAYLOAD))
    for name, size in [("elevation-A.dxf", (168, 96)), ("elevation-C.dxf", (91.5, 36))]:
        doc = _dxf(archive, name)
        assert doc.units == units.IN
        outlines = list(doc.modelspace().query('LWPOLYLINE[layer=="WALLS"]'))
        assert len(outlines) == 1
        assert outlines[0].closed
        length, height = size
        assert [tuple(p) for p in outlines[0].get_points("xy")] == [
            (0, 0), (length, 0), (length, height), (0, height),
        ]
    texts = [t.dxf.text for t in _dxf(archive, "elevation-D.dxf").modelspace().query("TEXT")]
    assert texts == ["ELEVATION D", "Wall 4 (back)", "G1 Euro kitchen"]


def test_zip_carries_the_payload_it_drew():
    assert json.loads(_zip(draw(PAYLOAD)).read("payload.json")) == PAYLOAD


def test_rejects_unknown_fields():
    payload = copy.deepcopy(PAYLOAD)
    payload["elevations"][0]["depth"] = 24
    with pytest.raises(ValidationError):
        draw(payload)


def test_rejects_other_payload_versions():
    with pytest.raises(ValidationError):
        draw({**PAYLOAD, "payloadVersion": 2})


def _cli(payload):
    return subprocess.run(
        [sys.executable, "-m", "src", "draw"],
        input=json.dumps(payload), capture_output=True, text=True, cwd=ROOT,
    )


def test_cli_draw_writes_the_result_to_stdout():
    run = _cli(PAYLOAD)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["files"][0] == "elevation-A.dxf"


def test_cli_draw_rejects_a_bad_payload_with_exit_2():
    run = _cli({**PAYLOAD, "units": "mm"})
    assert run.returncode == 2
    assert json.loads(run.stderr)["error"] == "Invalid drawing payload"
