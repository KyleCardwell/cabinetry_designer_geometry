"""Render a room's plan as a DXF (SPEC-44)."""

from shapely.geometry import Polygon
from shapely.ops import unary_union

from src.dxf.writer import TEXT_STYLE, create_dxf_document, doc_to_bytes

from .dimensions import DEFAULT_PLOT_SCALE
from .elevation_dxf import _add_hatch, _polygons
from .models import PayloadPlan, PayloadRoom


PLAN_LAYERS = {
    "opening": "OPENINGS",
    "casing": "OPENINGS",
    "recess": "WALLS",
    "soffit": "WALLS",
    "cabinet": "CABINETS",
    "face": "FACES",
    "filler": "FILLERS",
    "end_panel": "PANELS",
    "panel": "PANELS",
    "wall_end_panel": "PANELS",
    "frame": "FRAMES",
    "shelf": "SHELVES",
}

# Walls are joined 0.001" fat so mitre points that differ by noise still meet.
SNAP = 1e-3


def wall_region(plan: PayloadPlan):
    walls = [
        Polygon(part.points).buffer(SNAP, join_style="mitre")
        for part in plan.parts if part.kind == "wall"
    ]
    region = unary_union(walls).buffer(-SNAP, join_style="mitre")
    voids = [Polygon(part.points) for part in plan.parts if part.kind == "void"]
    if voids:
        region = region.difference(unary_union(voids))
    return region


def build_plan_dxf(
    plan: PayloadPlan, room: PayloadRoom, plot_scale: float = DEFAULT_PLOT_SCALE,
) -> bytes:
    doc = create_dxf_document()
    doc.header["$LTSCALE"] = plot_scale / 2
    modelspace = doc.modelspace()
    region = wall_region(plan)
    for polygon in _polygons(region):
        for ring in [polygon.exterior, *polygon.interiors]:
            modelspace.add_lwpolyline(
                list(ring.coords)[:-1], close=True, dxfattribs={"layer": "WALLS"},
            )
    _add_hatch(modelspace, "SECTIONS", region)

    for part in plan.parts:
        if part.kind in {"wall", "void"}:
            continue
        attributes = {"layer": PLAN_LAYERS[part.kind]}
        if part.dashed:
            attributes["linetype"] = "DASHED"
        modelspace.add_lwpolyline(part.points, close=part.closed, dxfattribs=attributes)

    points = [point for part in plan.parts for point in part.points]
    if points:
        left = min(x for x, _ in points)
        low = min(y for _, y in points)
        for text, position, height in [
            ("PLAN", (left, low - 12), 4),
            (room.name, (left, low - 18), 3),
        ]:
            modelspace.add_text(
                text,
                dxfattribs={"layer": "TEXT", "style": TEXT_STYLE, "insert": position, "height": height},
            )

    return doc_to_bytes(doc)
