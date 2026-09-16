"""Tests for in-memory DXF serialization."""

import io

import ezdxf

from src.dxf.writer import create_dxf_document, doc_to_bytes


def test_doc_to_bytes_produces_readable_dxf():
    doc = create_dxf_document()
    doc.modelspace().add_line((0, 0), (24, 0), dxfattribs={"layer": "WALLS"})

    dxf_bytes = doc_to_bytes(doc)

    assert isinstance(dxf_bytes, bytes)
    reopened = ezdxf.read(io.StringIO(dxf_bytes.decode(doc.output_encoding)))
    lines = list(reopened.modelspace().query("LINE"))
    assert len(lines) == 1
    assert lines[0].dxf.layer == "WALLS"
