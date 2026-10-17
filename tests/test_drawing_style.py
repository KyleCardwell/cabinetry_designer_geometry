"""The drawing style (SPEC-43.1, 50.15): one text style in Arial, lineweights per layer, dashes sized for paper."""

import base64
import copy
import io
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest
from ezdxf.fonts import fonts

from src.drawing.bundle import draw
from src.dxf.writer import LAYER_DEFS, create_dxf_document

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = json.loads((ROOT / "tests" / "fixtures" / "g1_payload.json").read_text())


def _dxf(payload, letter="A"):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(draw(payload)["zip_base64"])))
    return ezdxf.read(io.StringIO(archive.read(f"elevation-{letter}.dxf").decode("utf-8")))


def test_one_text_style_in_arial_for_labels_and_dimensions():
    doc = _dxf(PAYLOAD)
    style = doc.styles.get("FF_TEXT")
    assert style.dxf.font == "arial.ttf"
    assert style.get_extended_font_data() == ("Arial", False, False)
    assert {text.dxf.style for text in doc.modelspace().query("TEXT")} == {"FF_TEXT"}
    assert doc.dimstyles.get("FF").dxf.dimtxsty == "FF_TEXT"


def test_arial_label_widths_fit_the_designer_estimate():
    if not fonts.font_manager.has_font("arial.ttf"):
        pytest.skip("Arial (arial.ttf) is not installed or available to ezdxf; cannot measure its label widths")
    font = fonts.make_font("arial.ttf", cap_height=1)
    for text in ("24 15/16", "105 1/2", "CL 3", "TK 7"):
        width = font.text_width(text)
        assert width <= 0.7 * len(text), f"{text!r}: Arial width {width} exceeds the designer estimate"


def test_each_layer_has_its_lineweight_and_they_show():
    doc = create_dxf_document()
    weights = {layer.dxf.name: layer.dxf.lineweight for layer in doc.layers if layer.dxf.name not in ("0", "Defpoints")}
    assert weights == {
        "WALLS": 50, "CABINETS": 9, "FACES": 9, "FILLERS": 18, "PANELS": 18, "FRAMES": 18,
        "SHELVES": 18, "COUNTERTOPS": 35, "MOLDINGS": 18, "OPENINGS": 25, "SECTIONS": 13,
        "HIDDEN": 18, "DIMENSIONS": 18, "CENTERLINES": 18, "TEXT": 18, "MARKERS": 25,
        "DOOR_DETAILS": 9, "SWING_MARKS": 9, "PULLS": 13, "DOOR_TAGS": 18,
        "PART_NUMBERS": 18, "FRAME": 0,
    }
    assert doc.header["$LWDISPLAY"] == 1


def test_layer_colours_are_black_or_white_except_grey_hidden_and_sections_and_red_part_numbers():
    doc = _dxf(PAYLOAD)
    for name in LAYER_DEFS:
        expected = 1 if name == "PART_NUMBERS" else 8 if name in {"HIDDEN", "SECTIONS"} else 7
        assert doc.layers.get(name).dxf.color == expected
    assert all(entity.dxf.color == 256 for entity in doc.modelspace())


def test_dashes_are_sized_for_paper_at_the_plot_scale():
    assert _dxf(PAYLOAD).header["$LTSCALE"] == 12
    payload = copy.deepcopy(PAYLOAD)
    payload["plotScale"] = 48
    assert _dxf(payload).header["$LTSCALE"] == 24
