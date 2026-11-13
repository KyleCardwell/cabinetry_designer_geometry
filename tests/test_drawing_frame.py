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
from src.dxf.writer import create_dxf_document, doc_to_bytes, frame_drawing

ROOT = Path(__file__).resolve().parent.parent
ELEVATIONS = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())
PLAN = {"parts": [
    {"id": "base", "kind": "cabinet", "top": 34.5, "points": [[0, 0], [36, 0], [36, -24], [0, -24]]},
]}


def _dxf(payload, name):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read(name).decode("utf-8")))


@pytest.mark.parametrize("scale, name", [
    (24, "plan.dxf"), (48, "plan.dxf"), (24, "elevation-A.dxf"), (48, "elevation-A.dxf"),
])
def test_extents_limits_and_view_leave_half_an_inch_of_paper_around_everything(scale, name):
    doc = _dxf({**ELEVATIONS, "plan": PLAN, "plotScale": scale}, name)
    drawn = bbox.extents(entity for entity in doc.modelspace() if entity.dxf.layer != "FRAME")
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
    assert view.dxf.aspect_ratio == pytest.approx((high[0] - low[0]) / (high[1] - low[1]))
    framed = bbox.extents(doc.modelspace())
    assert tuple(framed.extmin) == pytest.approx((*low, 0))
    assert tuple(framed.extmax) == pytest.approx((*high, 0))


@pytest.mark.parametrize("scale, corner, low, high, center, height, aspect_ratio", [
    (24, (300, 100), (-12, -12), (312, 112), (150, 50), 124, 324 / 124),
    (48, (100, 200), (-24, -24), (124, 224), (50, 100), 248, 148 / 248),
])
def test_frame_matches_wide_and_tall_anchor_cases(scale, corner, low, high, center, height, aspect_ratio):
    doc = create_dxf_document()
    doc.modelspace().add_line((0, 0), corner, dxfattribs={"layer": "WALLS"})
    frame_drawing(doc, scale)
    doc = ezdxf.read(io.StringIO(doc_to_bytes(doc).decode(doc.output_encoding)))

    assert tuple(doc.header["$EXTMIN"]) == pytest.approx((*low, 0))
    assert tuple(doc.header["$EXTMAX"]) == pytest.approx((*high, 0))
    assert tuple(doc.header["$LIMMIN"]) == pytest.approx(low)
    assert tuple(doc.header["$LIMMAX"]) == pytest.approx(high)
    view = doc.viewports.get("*Active")[0]
    assert tuple(view.dxf.center) == pytest.approx((*center, 0))
    assert view.dxf.height == pytest.approx(height)
    assert view.dxf.aspect_ratio == pytest.approx(aspect_ratio)
    points = [entity for entity in doc.modelspace() if entity.dxf.layer == "FRAME"]
    assert len(points) == 4
    assert all(entity.dxftype() == "POINT" for entity in points)
    corners = (low, (high[0], low[1]), high, (low[0], high[1]))
    for point, corner in zip(points, corners):
        assert tuple(point.dxf.location) == pytest.approx((*corner, 0))


def test_draw_frame_points_are_invisible_on_a_plotting_layer():
    doc = _dxf(ELEVATIONS, "elevation-A.dxf")
    assert doc.header["$PDMODE"] == 1
    assert doc.header["$PDSIZE"] == 0
    layer = doc.layers.get("FRAME")
    assert layer.dxf.color == 7
    assert layer.dxf.linetype == "CONTINUOUS"
    assert layer.dxf.lineweight == 0
    assert layer.dxf.plot == 1


def test_empty_modelspace_keeps_header_and_view_without_frame_points():
    doc = create_dxf_document()
    header = {key: doc.header[key] for key in ("$EXTMIN", "$EXTMAX", "$LIMMIN", "$LIMMAX")}
    view = doc.viewports.get("*Active")[0].dxf.all_existing_dxf_attribs().copy()
    frame_drawing(doc, 24)
    assert len(doc.modelspace()) == 0
    assert {key: doc.header[key] for key in header} == header
    assert doc.viewports.get("*Active")[0].dxf.all_existing_dxf_attribs() == view
