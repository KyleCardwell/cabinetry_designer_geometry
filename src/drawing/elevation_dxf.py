"""Render a wall face and its labels as an elevation DXF."""

from src.dxf.writer import create_dxf_document, doc_to_bytes

from .models import PayloadElevation, PayloadRoom


def build_elevation_dxf(elevation: PayloadElevation, room: PayloadRoom) -> bytes:
    doc = create_dxf_document()
    modelspace = doc.modelspace()
    modelspace.add_lwpolyline(
        [
            (0, 0),
            (elevation.length, 0),
            (elevation.length, elevation.height),
            (0, elevation.height),
        ],
        close=True,
        dxfattribs={"layer": "WALLS"},
    )

    wall_label = elevation.wallLabel
    if elevation.side == "back":
        wall_label += " (back)"
    for text, position, height in [
        (elevation.title.upper(), (0, -12), 4),
        (wall_label, (0, -18), 3),
        (room.name, (0, -23), 3),
    ]:
        modelspace.add_text(
            text,
            dxfattribs={"layer": "TEXT", "insert": position, "height": height},
        )

    return doc_to_bytes(doc)
