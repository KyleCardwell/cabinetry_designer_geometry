"""PDF paper, scale, rendering and shared-document anchors (SPEC-50.15)."""

import base64
import io
import json
import logging
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import ezdxf
import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from pypdf.generic import ContentStream

from src.drawing import bundle, elevation_dxf, plan_dxf
from src.drawing.models import DrawingPayload
from src.drawing.pdf import fit_page, render_pdf, scale_label
from src.dxf.writer import create_dxf_document, doc_to_bytes, frame_drawing
from tests.test_drawing_frame import ELEVATIONS, PLAN

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("frame, paper, expected", [
    ((240, 120), "letter", (11, 8.5, 24, True)),
    ((120, 200), "letter", (8.5, 11, 24, True)),
    ((480, 120), "letter", (11, 8.5, 480 / 10.5, False)),
    ((480, 120), "archD", (36, 24, 24, True)),
    ((480, 120), "ledger", (17, 11, 480 / 16.5, False)),
    ((252, 192), "letter", (11, 8.5, 24, True)),
    # Shrinking can prefer portrait; equal shrink factors still prefer landscape.
    ((120, 480), "letter", (8.5, 11, 480 / 10.5, False)),
    ((480, 480), "letter", (11, 8.5, 60, False)),
])
def test_fit_page_anchors(frame, paper, expected):
    w, h, scale, to_scale = fit_page(*frame, paper, 24)
    assert (w, h, scale) == pytest.approx(expected[:3])
    assert to_scale is expected[3]
    assert scale >= 24


def test_scale_label_anchors_and_remaining_architectural_scales():
    for scale, expected in [
        (24, 'SCALE 1/2" = 1\'-0"'), (48, 'SCALE 1/4" = 1\'-0"'),
        (20, 'SCALE 1:20'), (12, 'SCALE 1" = 1\'-0"'),
        (16, 'SCALE 3/4" = 1\'-0"'), (32, 'SCALE 3/8" = 1\'-0"'),
    ]:
        assert scale_label(scale, True) == expected
    assert scale_label(24, False) == "NOT TO SCALE"


@pytest.mark.parametrize("paper, points", [
    (None, (612, 792)), ("archD", (1728, 2592)), ("ledger", (792, 1224)),
])
def test_bundle_paper_page_order_and_shared_documents(paper, points, monkeypatch, caplog):
    payload = {**ELEVATIONS, "plan": PLAN}
    if paper is not None:
        payload["paperSize"] = paper
    written = []
    serialized = []
    original_write, original_render = bundle.doc_to_bytes, bundle.render_pdf

    def write(doc):
        written.append(doc)
        data = original_write(doc)
        serialized.append(data)
        return data

    def render(docs, paper, scale, revision=None):
        assert revision is None
        assert len(docs) == len(written)
        assert all(doc is written[index] for index, doc in enumerate(docs))
        titles = [list(doc.modelspace().query("TEXT"))[0].dxf.text for doc in docs]
        assert titles == ["PLAN", *[elevation["title"].upper() for elevation in ELEVATIONS["elevations"]]]
        return original_render(docs, paper, scale, revision=revision)

    monkeypatch.setattr(bundle, "doc_to_bytes", write)
    monkeypatch.setattr(bundle, "render_pdf", render)
    caplog.set_level(logging.INFO, logger="src.drawing.pdf")
    result = bundle.draw(payload)
    expected = ["plan.dxf", *[f'elevation-{e["letter"]}.dxf' for e in ELEVATIONS["elevations"]], "drawings.pdf"]
    assert result["files"] == expected
    with ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as archive:
        assert archive.namelist() == ["payload.json", *expected]
        assert json.loads(archive.read("payload.json")) == payload
        assert [archive.read(name) for name in expected[:-1]] == serialized
        reader = PdfReader(io.BytesIO(archive.read("drawings.pdf")))
    assert len(reader.pages) == 1 + len(ELEVATIONS["elevations"])
    for page in reader.pages:
        size = (float(page.mediabox.width), float(page.mediabox.height))
        assert size == points or size == points[::-1]
    doc = written[0]
    low, high = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
    assert fit_page(high[0] - low[0], high[1] - low[1], paper or "letter", 24)[3]
    assert caplog.records[0].getMessage() == 'PDF page 1 scale note: SCALE 1/2" = 1\'-0"'
    assert not any(" revision: " in record.getMessage() for record in caplog.records)


def test_revision_on_every_page_and_identical_dxf_bytes(monkeypatch, caplog):
    from matplotlib.backends.backend_pdf import PdfPages

    monkeypatch.setattr(ezdxf.options, "write_fixed_meta_data_for_testing", True)
    payload = {**ELEVATIONS, "plan": PLAN, "paperSize": "letter"}
    original_result = bundle.draw(payload)
    revision = "KC 10/15/26 (v2)"
    payload["room"] = {**payload["room"], "revision": revision}
    original_save = PdfPages.savefig
    pages = []

    def save(pdf, fig, **kwargs):
        assert len(fig.texts) == 2
        scale_note, revision_note = fig.texts
        assert revision_note.get_text() == revision
        assert revision_note.get_position() == (3 / 16, 3 / 16)
        assert revision_note.get_transform() is fig.dpi_scale_trans
        assert revision_note.get_ha() == "left"
        assert revision_note.get_va() == "bottom"
        assert revision_note.get_fontfamily() == scale_note.get_fontfamily()
        assert revision_note.get_fontsize() == scale_note.get_fontsize() == 9
        assert revision_note.get_color() == scale_note.get_color() == "black"
        pages.append(fig)
        return original_save(pdf, fig, **kwargs)

    monkeypatch.setattr(PdfPages, "savefig", save)
    caplog.set_level(logging.INFO, logger="src.drawing.pdf")
    result = bundle.draw(payload)
    with (
        ZipFile(io.BytesIO(base64.b64decode(original_result["zip_base64"]))) as original,
        ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as archive,
    ):
        assert json.loads(archive.read("payload.json"))["room"]["revision"] == revision
        for name in result["files"]:
            if name.endswith(".dxf"):
                assert archive.read(name) == original.read(name)
        reader = PdfReader(io.BytesIO(archive.read("drawings.pdf")))
        assert len(reader.pages) == len(pages) == 1 + len(ELEVATIONS["elevations"])
        assert all(revision in page.extract_text() for page in reader.pages)
    assert [record.getMessage() for record in caplog.records if " revision: " in record.getMessage()] == [
        f"PDF page {page} revision: {revision}" for page in range(1, len(pages) + 1)
    ]


@pytest.mark.parametrize("revision", [None, "", "   "])
def test_missing_or_blank_revision_prints_and_logs_nothing(revision, monkeypatch, caplog):
    from matplotlib.backends.backend_pdf import PdfPages

    payload = {**ELEVATIONS, "plan": PLAN}
    if revision is not None:
        payload["room"] = {**payload["room"], "revision": revision}
    original_save = PdfPages.savefig
    pages = []

    def save(pdf, fig, **kwargs):
        assert len(fig.texts) == 1
        assert fig.texts[0].get_ha() == "right"
        pages.append(fig)
        return original_save(pdf, fig, **kwargs)

    monkeypatch.setattr(PdfPages, "savefig", save)
    caplog.set_level(logging.INFO, logger="src.drawing.pdf")
    result = bundle.draw(payload)
    assert len(pages) == 1 + len(ELEVATIONS["elevations"])
    assert not any(" revision: " in record.getMessage() for record in caplog.records)
    with ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as archive:
        saved_room = json.loads(archive.read("payload.json"))["room"]
        if revision is None:
            assert "revision" not in saved_room
        else:
            assert saved_room["revision"] == revision


def test_revision_length_limit_and_cli_exit_2():
    payload = {**ELEVATIONS, "room": {**ELEVATIONS["room"], "revision": "R" * 80}}
    assert DrawingPayload.model_validate(payload).room.revision == "R" * 80
    payload["room"]["revision"] += "R"
    with pytest.raises(ValidationError) as error:
        bundle.draw(payload)
    assert error.value.errors()[0]["loc"] == ("room", "revision")
    assert error.value.errors()[0]["type"] == "string_too_long"
    run = subprocess.run(
        [sys.executable, "-m", "src", "draw"], input=json.dumps(payload),
        capture_output=True, text=True, cwd=ROOT,
    )
    assert run.returncode == 2
    assert json.loads(run.stderr)["error"] == "Invalid drawing payload"


def test_invalid_paper_is_a_validation_error_and_cli_exit_2():
    payload = {**ELEVATIONS, "paperSize": "a4"}
    with pytest.raises(ValidationError):
        bundle.draw(payload)
    run = subprocess.run(
        [sys.executable, "-m", "src", "draw"], input=json.dumps(payload),
        capture_output=True, text=True, cwd=ROOT,
    )
    assert run.returncode == 2
    assert json.loads(run.stderr)["error"] == "Invalid drawing payload"


def test_no_drawings_means_no_pdf():
    result = bundle.draw({**ELEVATIONS, "elevations": []})
    assert result["files"] == []
    with ZipFile(io.BytesIO(base64.b64decode(result["zip_base64"]))) as archive:
        assert archive.namelist() == ["payload.json"]


@pytest.mark.parametrize("scale", [24, 48])
def test_dxf_wrappers_serialize_the_framed_document_without_changing_bytes(scale, monkeypatch):
    monkeypatch.setattr(ezdxf.options, "write_fixed_meta_data_for_testing", True)
    model = DrawingPayload.model_validate({**ELEVATIONS, "plan": PLAN})
    for make, build, drawing in [
        (plan_dxf.make_plan_doc, plan_dxf.build_plan_dxf, model.plan),
        (elevation_dxf.make_elevation_doc, elevation_dxf.build_elevation_dxf, model.elevations[0]),
    ]:
        doc = make(drawing, model.room, scale)
        assert tuple(doc.header["$EXTMIN"]) == tuple(doc.modelspace().dxf.extmin)
        assert tuple(doc.header["$EXTMAX"]) == tuple(doc.modelspace().dxf.extmax)
        assert doc_to_bytes(doc) == build(drawing, model.room, scale)


def test_render_preserves_page_scale_lineweights_colours_and_invisible_points(monkeypatch, caplog):
    from matplotlib.backends.backend_pdf import PdfPages

    doc = create_dxf_document()
    msp = doc.modelspace()
    msp.add_line((0, 0), (456, 96), dxfattribs={"layer": "WALLS"})
    msp.add_line((0, 96), (456, 0), dxfattribs={"layer": "PART_NUMBERS"})
    msp.add_line((0, 24), (456, 24), dxfattribs={"layer": "FACES"})
    msp.add_line((0, 48), (456, 48), dxfattribs={"layer": "DOOR_DETAILS"})
    msp.add_line((0, 72), (456, 72), dxfattribs={"layer": "SECTIONS"})
    hatch = msp.add_hatch(dxfattribs={"layer": "SECTIONS"})
    hatch.set_solid_fill(color=256)
    hatch.paths.add_polyline_path([(0, 0), (20, 0), (20, 20), (0, 20)], is_closed=True)
    frame_drawing(doc, 24)
    doc.update_extents()
    original_save = PdfPages.savefig

    def save(pdf, fig, **kwargs):
        result = original_save(pdf, fig, **kwargs)
        ax = fig.axes[0]
        assert tuple(fig.get_size_inches()) == (11, 8.5)
        assert ax.get_position().bounds == pytest.approx((0, 0, 1, 1))
        assert ax.get_xlim() == pytest.approx((228 - 11 * (480 / 10.5) / 2, 228 + 11 * (480 / 10.5) / 2))
        assert ax.get_ylim() == pytest.approx((48 - 8.5 * (480 / 10.5) / 2, 48 + 8.5 * (480 / 10.5) / 2))
        assert not ax.axison
        # The frame's PDMODE=1 points produce no scatter collections.
        assert not ax.collections
        note = fig.texts[0]
        assert note.get_text() == "NOT TO SCALE"
        assert note.get_position() == (11 - 3 / 16, 3 / 16)
        assert note.get_ha() == "right"
        assert note.get_fontfamily()[0] in {"Arial", "Liberation Sans", "Arimo", "sans-serif"}
        assert note.get_fontsize() == 9
        assert note.get_color() == "black"
        return result

    monkeypatch.setattr(PdfPages, "savefig", save)
    caplog.set_level(logging.INFO, logger="src.drawing.pdf")
    reader = PdfReader(io.BytesIO(render_pdf([doc], "letter", 24)))
    page = reader.pages[0]
    assert (page.mediabox.width, page.mediabox.height) == (792, 612)
    assert caplog.records[0].getMessage() == "PDF page 1 scale note: NOT TO SCALE"
    objects = page["/Resources"]["/XObject"].get_object()
    assert all(obj.get_object()["/Subtype"] != "/Image" for obj in objects.values())
    operations = ContentStream(page.get_contents(), reader).operations
    widths = [float(args[0]) for args, op in operations if op == b"w"]
    assert any(width == pytest.approx(0.50 * 72 / 25.4) for width in widths)
    assert any(width == pytest.approx(0.18 * 72 / 25.4) for width in widths)
    assert any(width == pytest.approx(0.13 * 72 / 25.4) for width in widths)
    assert any(width == pytest.approx(0.09 * 72 / 25.4) for width in widths)
    assert any(list(args) == [1, 0, 0] for args, op in operations if op == b"RG")
    assert any(list(args) in ([0], [0, 0, 0]) for args, op in operations if op in (b"G", b"RG"))
    assert any(0 < float(args[0]) < 1 and len(set(args)) == 1 for args, op in operations if op in (b"g", b"rg"))
