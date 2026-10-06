"""Render a wall face and its labels as an elevation DXF."""

from shapely.geometry import Polygon

from src.dxf.writer import TEXT_STYLE, add_dimstyle, create_dxf_document, doc_to_bytes, write_lines_to_layer
from src.projection.hlr import EPSILON, HlrShape, hidden_line_removal, rect_polygon, visible_regions

from .dimensions import DEFAULT_PLOT_SCALE, add_dimensions
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
    "wall_end_panel": "PANELS",
    "opening": "OPENINGS",
    "casing": "OPENINGS",
    "soffit": "WALLS",
    "recess": "WALLS",
    "projection": "WALLS",
    "wing_wall": "WALLS",
    "section": "SECTIONS",
    "profile": "CABINETS",
}

# Kinds drawn hatched where they show (SPEC-42.2): a neighbour cut where it meets this wall face.
HATCHED = {"section"}
# ANSI31 lines are 1/8" apart at scale 1; 8 puts them 1" apart in the drawing (1/24" on paper at 1/2" = 1'-0").
HATCH_SCALE = 8

# Kinds whose hidden edges are left out rather than dashed (SPEC-42).
NEVER_DASHED = {"toe_kick", "top_mold", "crown"}


def _edge_lines(part) -> tuple:
    """A part's own lines, plus its rectangle's sides when some are left open (SPEC-42.1)."""
    lines = tuple(((line.x1, line.z1), (line.x2, line.z2)) for line in part.lines)
    if not part.openEdges:
        return lines
    left, right, bottom, top = part.x, part.x + part.width, part.z, part.z + part.height
    sides = {
        "bottom": ((left, bottom), (right, bottom)),
        "right": ((right, bottom), (right, top)),
        "top": ((left, top), (right, top)),
        "left": ((left, bottom), (left, top)),
    }
    return tuple(side for name, side in sides.items() if name not in part.openEdges) + lines


def _polygons(region) -> list:
    """The non-empty polygons in a shapely region (a Polygon, MultiPolygon or GeometryCollection)."""
    if isinstance(region, Polygon):
        return [] if region.is_empty else [region]
    return [part for geom in getattr(region, "geoms", []) for part in _polygons(geom)]


def _add_hatch(modelspace, layer, region) -> None:
    """One ANSI31 hatch per polygon of a region, holes included (SPEC-42.2)."""
    for polygon in _polygons(region):
        if polygon.area <= EPSILON:
            continue
        hatch = modelspace.add_hatch(dxfattribs={"layer": layer})
        hatch.set_pattern_fill("ANSI31", scale=HATCH_SCALE)
        hatch.paths.add_polyline_path(list(polygon.exterior.coords)[:-1], is_closed=True, flags=1)
        for ring in polygon.interiors:
            hatch.paths.add_polyline_path(list(ring.coords)[:-1], is_closed=True, flags=16)


def build_elevation_dxf(
    elevation: PayloadElevation, room: PayloadRoom, plot_scale: float = DEFAULT_PLOT_SCALE,
) -> bytes:
    doc = create_dxf_document()
    add_dimstyle(doc, plot_scale)
    # Dashes 1/4" and gaps 1/8" on paper at any plot scale (SPEC-43.1): DASHED is 1/2" + 1/4" at LTSCALE 1.
    doc.header["$LTSCALE"] = plot_scale / 2
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
            lines=_edge_lines(part),
            opaque=part.opaque,
            outlined=not part.openEdges,
        )
        for part in parts
    ]
    lines = hidden_line_removal(shapes)
    for part in parts:
        visible, hidden = lines[part.id]
        write_lines_to_layer(doc, KIND_LAYERS[part.kind], visible)
        write_lines_to_layer(doc, "HIDDEN", hidden)

    regions = visible_regions(shapes, {part.id for part in parts if part.kind in HATCHED})
    for part in parts:
        if part.id in regions:
            _add_hatch(modelspace, KIND_LAYERS[part.kind], regions[part.id])

    add_dimensions(modelspace, elevation.dimensions)

    # The title sits under the lowest dimension line or moved text (SPEC-43, 43.1); with none, where it always has.
    low = min([
        0.0,
        *(dimension.at for dimension in elevation.dimensions),
        *(dimension.textZ for dimension in elevation.dimensions if dimension.textZ is not None),
    ])

    wall_label = elevation.wallLabel
    if elevation.side == "back":
        wall_label += " (back)"
    for text, position, height in [
        (elevation.title.upper(), (0, low - 12), 4),
        (wall_label, (0, low - 18), 3),
        (room.name, (0, low - 23), 3),
    ]:
        modelspace.add_text(
            text,
            dxfattribs={"layer": "TEXT", "style": TEXT_STYLE, "insert": position, "height": height},
        )

    return doc_to_bytes(doc)
