"""Wall end panels, openings, soffits, recesses and wing walls (SPEC-42.1)."""

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
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "walls_payload.json").read_text())


def _archive(payload):
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))


def _modelspace(payload):
    dxf = _archive(payload).read("elevation-A.dxf").decode("utf-8")
    return ezdxf.read(io.StringIO(dxf)).modelspace()


def _lines(msp, layer):
    return list(msp.query(f'LINE[layer=="{layer}"]'))


def _length(lines):
    return sum(line.dxf.start.distance(line.dxf.end) for line in lines)


def test_wall_things_draw_on_panels_openings_and_walls():
    msp = _modelspace(PAYLOAD)
    assert _length(_lines(msp, "PANELS")) == pytest.approx(70.5)  # the wall end panel
    assert len(_lines(msp, "OPENINGS")) == 8  # casing and opening, both whole
    assert _length(_lines(msp, "OPENINGS")) == pytest.approx(458)
    assert len(_lines(msp, "WALLS")) == 12  # recess 5, soffit 3, wing wall 4
    assert _length(_lines(msp, "WALLS")) == pytest.approx(578.5)


def test_outlines_hide_nothing_but_are_hidden_behind_cabinets():
    msp = _modelspace(PAYLOAD)
    # Both boxes draw whole: the one in the recess isn't hidden by the recess outline in front of it.
    assert _length(_lines(msp, "CABINETS")) == pytest.approx(222)
    hidden = _lines(msp, "HIDDEN")
    assert len(hidden) == 1  # the recess's left edge behind the face cabinet
    assert [hidden[0].dxf.start.x, hidden[0].dxf.end.x] == pytest.approx([60, 60])
    assert sorted([hidden[0].dxf.start.y, hidden[0].dxf.end.y]) == pytest.approx([4, 34.5])


def test_open_edges_round_trip_and_bad_values_are_rejected():
    stored = json.loads(_archive(PAYLOAD).read("payload.json"))
    assert stored == PAYLOAD  # runId left out, opaque and openEdges kept
    for patch in ({"openEdges": ["front"]}, {"opaque": "maybe"}, {"kind": "window"}):
        bad = copy.deepcopy(PAYLOAD)
        bad["elevations"][0]["parts"][5].update(patch)
        with pytest.raises(ValidationError):
            draw(bad)
