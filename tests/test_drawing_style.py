"""The drawing style (SPEC-43.1): one text style in Arial Narrow, lineweights per layer, dashes sized for paper."""

import base64
import copy
import io
import json
import zipfile
from pathlib import Path

import ezdxf

from src.drawing.bundle import draw
from src.dxf.writer import create_dxf_document

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())


def _dxf(payload, letter="A"):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read(f"elevation-{letter}.dxf").decode("utf-8")))


def test_one_text_style_in_arial_narrow_for_labels_and_dimensions():
    doc = _dxf(PAYLOAD)
    style = doc.styles.get("FF_TEXT")
    assert style.dxf.font == "arialn.ttf"
    assert style.get_extended_font_data() == ("Arial Narrow", False, False)
    assert {text.dxf.style for text in doc.modelspace().query("TEXT")} == {"FF_TEXT"}
    assert doc.dimstyles.get("FF").dxf.dimtxsty == "FF_TEXT"


def test_each_layer_has_its_lineweight_and_they_show():
    doc = create_dxf_document()
    weights = {layer.dxf.name: layer.dxf.lineweight for layer in doc.layers if layer.dxf.name not in ("0", "Defpoints")}
    assert weights == {
        "WALLS": 50, "CABINETS": 35, "FACES": 25, "FILLERS": 25, "PANELS": 25, "FRAMES": 25,
        "SHELVES": 18, "COUNTERTOPS": 35, "MOLDINGS": 25, "OPENINGS": 25, "SECTIONS": 25,
        "HIDDEN": 18, "DIMENSIONS": 18, "TEXT": 18,
    }
    assert doc.header["$LWDISPLAY"] == 1


def test_dashes_are_sized_for_paper_at_the_plot_scale():
    assert _dxf(PAYLOAD).header["$LTSCALE"] == 12
    payload = copy.deepcopy(PAYLOAD)
    payload["plotScale"] = 48
    assert _dxf(payload).header["$LTSCALE"] == 24
