"""Centreline marks in the elevation DXF (SPEC-43.3)."""

import base64
import copy
import io
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment
from pydantic import ValidationError

from src.drawing.bundle import draw

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())

# G1 elevation A: the sink pinned to the window's centre with no offset, as the designer sends it (SPEC-43.3).
MARK = {"kind": "centerline", "x": 72, "bottom": 4, "top": 66, "text": "CL", "textX": 72, "textZ": 68.625}


def _payload(plot_scale=None):
    payload = copy.deepcopy(PAYLOAD)
    payload["elevations"][0]["marks"] = [copy.deepcopy(MARK)]
    if plot_scale is not None:
        payload["plotScale"] = plot_scale
    return payload


def _dxf(payload, letter="A"):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read(f"elevation-{letter}.dxf").decode("utf-8")))


def test_a_centerline_mark_is_a_center_line_with_its_label():
    doc = _dxf(_payload())
    modelspace = doc.modelspace()
    [line] = modelspace.query('LINE[layer=="CENTERLINES"]')
    assert (tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2]) == ((72, 4), (72, 66))
    assert doc.layers.get("CENTERLINES").dxf.linetype == "CENTER"
    [label] = [text for text in modelspace.query("TEXT") if text.dxf.text == "CL"]
    assert (label.dxf.layer, label.dxf.style, label.dxf.height) == ("DIMENSIONS", "FF_TEXT", 2.25)
    align, point, _ = label.get_placement()
    assert (align, tuple(point)[:2]) == (TextEntityAlignment.MIDDLE_CENTER, (72, 68.625))
    assert list(_dxf(_payload(), "B").modelspace().query('LINE[layer=="CENTERLINES"]')) == []


def test_marks_scale_with_the_drawing_round_trip_and_reject_an_unknown_kind():
    [label] = [text for text in _dxf(_payload(plot_scale=48)).modelspace().query("TEXT") if text.dxf.text == "CL"]
    assert label.dxf.height == 4.5
    payload = _payload()
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    assert json.loads(archive.read("payload.json")) == payload
    payload["elevations"][0]["marks"][0]["kind"] = "arrow"
    with pytest.raises(ValidationError):
        draw(payload)
