"""Render a wall face and its labels as an elevation DXF."""

from src.dxf.writer import create_dxf_document, doc_to_bytes, write_lines_to_layer
from src.projection.hlr import EPSILON, HlrShape, hidden_line_removal, rect_polygon

from .models import PayloadElevation, PayloadRoom


KIND_LAYERS = {
    "cabinet": "CABINETS",
    "face": "FACES",
    "filler": "FILLERS",
    "end_panel": "PANELS",
    "panel": "PANELS",
    "frame": "FRAMES",
    "shelf": "SHELVES",
    "toe_kick": "MOLDINGS",
    "countertop": "COUNTERTOPS",
    "top_mold": "MOLDINGS",
    "crown": "MOLDINGS",
    "light_rail": "MOLDINGS",
    "light_trough": "MOLDINGS",
    "bottom_cap": "MOLDINGS",
    "corbels": "MOLDINGS",
}

# Kinds whose hidden edges are left out rather than dashed (SPEC-42).
NEVER_DASHED = {"toe_kick", "top_mold", "crown"}


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

    parts = [
        part for part in elevation.parts
        if part.width > EPSILON and part.height > EPSILON
    ]
    shapes = [
        HlrShape(
            id=part.id,
            polygon=rect_polygon(
                part.x, part.z, part.width, part.height,
                [(hole.x, hole.z, hole.width, hole.height) for hole in part.holes],
            ),
            front=part.front,
            is_box=part.kind == "cabinet",
            covers_box_edges=part.coversBoxEdges,
            drop_hidden=part.kind in NEVER_DASHED,
            lines=tuple(((line.x1, line.z1), (line.x2, line.z2)) for line in part.lines),
        )
        for part in parts
    ]
    lines = hidden_line_removal(shapes)
    for part in parts:
        visible, hidden = lines[part.id]
        write_lines_to_layer(doc, KIND_LAYERS[part.kind], visible)
        write_lines_to_layer(doc, "HIDDEN", hidden)

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
