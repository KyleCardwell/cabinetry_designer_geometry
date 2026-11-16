"""Readable entity summaries of every DXF in the GC0 golden drawing bundles."""

import base64
import io
import json
import os
from numbers import Integral, Real
from pathlib import Path
from zipfile import ZipFile

import ezdxf
import pytest
from ezdxf.math import Vec2, Vec3

from src.drawing.bundle import draw


TESTS = Path(__file__).resolve().parent
PAYLOADS = sorted((TESTS / "fixtures" / "golden").glob("*.payload.json"))
# Only database identity and references to generated database objects are excluded.
# DIMENSION.geometry and INSERT.name remain: they identify the summarized blocks.
IDENTITY = {"handle", "owner", "material_handle", "plotstyle_handle", "visualstyle_handle"}
ATTRIBUTE_GEOMETRY = {
    "LINE", "POINT", "ARC", "CIRCLE", "ELLIPSE", "SOLID", "TRACE", "3DFACE",
    "TEXT", "MTEXT", "DIMENSION", "INSERT", "ATTRIB", "ATTDEF", "VERTEX",
    "LWPOLYLINE", "POLYLINE", "HATCH",
}


def rounded(value):
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    if isinstance(value, (Vec2, Vec3, tuple, list)):
        return [rounded(item) for item in value]
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        result = round(float(value), 6)
        return 0.0 if result == 0 else result
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"Uncaptured DXF value: {type(value).__name__}")


def entity_summary(entity):
    kind = entity.dxftype()
    # Fail when a new entity needs extra geometry, rather than silently omit it.
    assert kind in ATTRIBUTE_GEOMETRY, f"Add geometry serialization for {kind}"
    result = {"type": kind, **entity.dxfattribs(drop=IDENTITY), "layer": entity.dxf.layer}
    if kind == "LWPOLYLINE":
        result["vertices"] = entity.get_points("xyseb")
    elif kind == "POLYLINE":
        result["vertices"] = [entity_summary(vertex) for vertex in entity.vertices]
    elif kind == "MTEXT":
        result["text"] = entity.text
    elif kind == "INSERT":
        result["attribs"] = summaries(entity.attribs)
    elif kind == "HATCH":
        paths = []
        for path in entity.paths:
            # The drawing writers emit polyline hatch boundaries, including holes.
            assert hasattr(path, "vertices"), "Add edge-path hatch serialization"
            paths.append({
                "flags": path.path_type_flags,
                "closed": path.is_closed,
                "vertices": path.vertices,
            })
        result["paths"] = paths
        result["pattern"] = entity.pattern.as_list() if entity.pattern else None
        result["seeds"] = entity.seeds
        assert entity.gradient is None, "Add gradient hatch serialization"
    # TEXT content, DIMENSION defpoints/text/geometry and INSERT block names are
    # ordinary DXF attributes and are retained above along with all other fields.
    return rounded(result)


def summaries(entities):
    return sorted(
        (entity_summary(entity) for entity in entities),
        key=lambda item: json.dumps(item, sort_keys=True),
    )


def document_summary(document):
    return {
        "modelspace": summaries(document.modelspace()),
        "blocks": {
            block.name: {
                "basePoint": rounded(block.base_point),
                "entities": summaries(block),
            }
            for block in document.blocks
        },
    }


@pytest.mark.parametrize("payload_path", PAYLOADS, ids=lambda path: path.name.removesuffix(".payload.json"))
def test_golden_dxf(payload_path):
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    # draw() returns a ZIP containing all DXFs and a PDF; only the DXFs are outputs here.
    bundle = draw(payload)
    with ZipFile(io.BytesIO(base64.b64decode(bundle["zip_base64"]))) as archive:
        dxf_names = sorted(name for name in archive.namelist() if name.endswith(".dxf"))
        assert dxf_names, f"No DXFs for {payload_path.name}: {payload['room']['name']}"
        actual = {
            name: document_summary(ezdxf.read(io.StringIO(archive.read(name).decode("utf-8"))))
            for name in dxf_names
        }
    expected = TESTS / "golden" / payload_path.name.replace(".payload.json", ".dxf.json")
    serialized = json.dumps(actual, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(serialized, encoding="utf-8")
    else:
        assert serialized == expected.read_text(encoding="utf-8")
