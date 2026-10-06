"""The space around every drawing (SPEC-44.1)."""

import base64
import io
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest
from ezdxf import bbox

from src.drawing.bundle import draw

ROOT = Path(__file__).resolve().parent.parent
ELEVATIONS = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())
PLAN = {"parts": [
    {"id": "base", "kind": "cabinet", "top": 34.5, "points": [[0, 0], [36, 0], [36, -24], [0, -24]]},
]}


def _dxf(payload, name):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read(name).decode("utf-8")))


@pytest.mark.parametrize("scale, name", [(24, "plan.dxf"), (48, "plan.dxf"), (24, "elevation-A.dxf")])
def test_extents_limits_and_view_leave_half_an_inch_of_paper_around_everything(scale, name):
    doc = _dxf({**ELEVATIONS, "plan": PLAN, "plotScale": scale}, name)
    drawn = bbox.extents(doc.modelspace())
    pad = 0.5 * scale
    low = (drawn.extmin.x - pad, drawn.extmin.y - pad)
    high = (drawn.extmax.x + pad, drawn.extmax.y + pad)
    assert tuple(doc.header["$EXTMIN"])[:2] == pytest.approx(low)
    assert tuple(doc.header["$EXTMAX"])[:2] == pytest.approx(high)
    assert tuple(doc.header["$LIMMIN"]) == pytest.approx(low)
    assert tuple(doc.header["$LIMMAX"]) == pytest.approx(high)
    view = doc.viewports.get("*Active")[0]
    assert tuple(view.dxf.center)[:2] == pytest.approx(((low[0] + high[0]) / 2, (low[1] + high[1]) / 2))
    assert view.dxf.height == pytest.approx(high[1] - low[1])
