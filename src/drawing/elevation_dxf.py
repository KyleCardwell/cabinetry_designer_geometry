"""Render a wall face and its labels as an elevation DXF."""

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import Polygon

from src.dxf.writer import DIMSTYLE_PAPER, TEXT_STYLE, add_dimstyle, create_dxf_document, doc_to_bytes, frame_drawing, write_arcs_to_layer, write_lines_to_layer
from src.projection.hlr import EPSILON, HlrShape, hidden_line_removal, rect_polygon, visible_regions

from .arcs import flatten_outline, rejoin_arcs
from .dimensions import DEFAULT_PLOT_SCALE, add_dimensions
from .marks import add_marks
from .models import PayloadElevation, PayloadRoom
from .part_numbers import add_part_numbers


KIND_LAYERS = {
    "cabinet": "CABINETS",
    "face": "FACES",
    "filler": "FILLERS",
    "end_panel": "PANELS",
    "panel": "PANELS",
    "frame": "FRAMES",
    "shelf": "SHELVES",
    "toe_kick": "MOLDINGS",
    "furniture_base": "MOLDINGS",
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
NEVER_DASHED = {"toe_kick", "furniture_base", "top_mold", "crown"}


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


def _opening_lines(openings) -> tuple:
    """The four sides of each door opening or profile line rectangle, in wall coordinates (SPEC-46.4, SPEC-50)."""
    lines = []
    for opening in openings:
        left, right = opening.x, opening.x + opening.width
        bottom, top = opening.z, opening.z + opening.height
        lines.extend([
            ((left, bottom), (right, bottom)),
            ((right, bottom), (right, top)),
            ((left, top), (right, top)),
            ((left, bottom), (left, top)),
        ])
    return tuple(lines)


def _add_tags(modelspace, details, by_id, plot_scale) -> None:
    """Style labels in each part's top-left corner, sized for paper (SPEC-46.4)."""
    for detail in details:
        if not detail.tag:
            continue
        h = DIMSTYLE_PAPER["dimtxt"] * plot_scale
        part = by_id[detail.partId]
        if part.width < 4 * h - 1e-9 or part.height < 2 * h - 1e-9:
            continue
        modelspace.add_text(
            detail.tag,
            height=h,
            dxfattribs={"layer": "DOOR_TAGS", "style": TEXT_STYLE},
        ).set_placement(
            (part.x + h / 2, part.z + part.height - h / 2), align=TextEntityAlignment.TOP_LEFT,
        )


def _polygons(region) -> list:
    """The non-empty polygons in a shapely region (a Polygon, MultiPolygon or GeometryCollection)."""
    if isinstance(region, Polygon):
        return [] if region.is_empty else [region]
    return [part for geom in getattr(region, "geoms", []) for part in _polygons(geom)]


def _add_interior_labels(modelspace, interiors, plot_scale) -> None:
    """Centre accessory text in boxes that fit its paper-scaled height and estimated width."""
    h = DIMSTYLE_PAPER["dimtxt"] * plot_scale
    for interior in interiors:
        for label in interior.labels:
            if label.height < h or label.width < 0.6 * h * len(label.text):
                continue
            modelspace.add_text(
                label.text,
                height=h,
                dxfattribs={"layer": "INTERIORS", "style": TEXT_STYLE},
            ).set_placement(
                (label.x + label.width / 2, label.z + label.height / 2),
                align=TextEntityAlignment.MIDDLE_CENTER,
            )


def _add_hatch(modelspace, layer, region, solid: bool = False) -> None:
    """One ANSI31 hatch per polygon of a region, holes included, or solid when asked (SPEC-44.1)."""
    for polygon in _polygons(region):
        if polygon.area <= EPSILON:
            continue
        hatch = modelspace.add_hatch(dxfattribs={"layer": layer})
        if solid:
            hatch.set_solid_fill(color=256)
        else:
            hatch.set_pattern_fill("ANSI31", scale=HATCH_SCALE)
        hatch.paths.add_polyline_path(list(polygon.exterior.coords)[:-1], is_closed=True, flags=1)
        for ring in polygon.interiors:
            hatch.paths.add_polyline_path(list(ring.coords)[:-1], is_closed=True, flags=16)


def make_elevation_doc(
    elevation: PayloadElevation, room: PayloadRoom, plot_scale: float = DEFAULT_PLOT_SCALE,
) -> Drawing:
    doc = create_dxf_document()
    add_dimstyle(doc, plot_scale)
    # Dashes 1/4" and gaps 1/8" on paper at any plot scale (SPEC-43.1): DASHED is 1/2" + 1/4" at LTSCALE 1.
    doc.header["$LTSCALE"] = plot_scale / 2
    modelspace = doc.modelspace()
    wall_outlines = [(0, elevation.length, elevation.height)] if elevation.faces is None else [
        (face.dx, face.length, face.height) for face in elevation.faces
    ]
    for x, length, height in wall_outlines:
        modelspace.add_lwpolyline(
            [(x, 0), (x + length, 0), (x + length, height), (x, height)],
            close=True,
            dxfattribs={"layer": "WALLS"},
        )
    for face in elevation.faces or []:
        if face.note is not None:
            modelspace.add_text(
                face.note,
                height=DIMSTYLE_PAPER["dimtxt"] * plot_scale,
                dxfattribs={"layer": "DIMENSIONS", "style": TEXT_STYLE},
            ).set_placement(
                (face.dx + face.length / 2, face.height - 0.25 * plot_scale),
                align=TextEntityAlignment.MIDDLE_CENTER,
            )

    parts = [
        part for part in elevation.parts
        if part.width > EPSILON and part.height > EPSILON
    ]
    outlines = {part.id: flatten_outline(part.outline) for part in parts if part.outline is not None}
    shapes = [
        HlrShape(
            id=part.id,
            polygon=Polygon(
                outlines[part.id][0],
                [[
                    (hole.x, hole.z), (hole.x + hole.width, hole.z),
                    (hole.x + hole.width, hole.z + hole.height), (hole.x, hole.z + hole.height),
                ] for hole in part.holes],
            ) if part.outline is not None else rect_polygon(
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
    by_id = {part.id: part for part in parts}
    detail_shapes = [
        HlrShape(
            id=f"{part.id}#door",
            polygon=rect_polygon(part.x, part.z, part.width, part.height),
            front=part.front,
            drop_hidden=True,
            lines=_opening_lines([*detail.openings, *detail.profileLines]) + tuple(
                ((line.x1, line.z1), (line.x2, line.z2)) for line in detail.miters
            ),
            opaque=False,
            outlined=False,
        )
        for detail in elevation.doorDetails if detail.openings or detail.profileLines or detail.miters
        for part in [by_id[detail.partId]]
    ]
    swing_shapes = [
        HlrShape(
            id=f"{part.id}#swing",
            polygon=rect_polygon(part.x, part.z, part.width, part.height),
            front=part.front,
            drop_hidden=True,
            lines=tuple(((line.x1, line.z1), (line.x2, line.z2)) for line in mark.lines),
            opaque=False,
            outlined=False,
        )
        for mark in elevation.swingMarks
        for part in [by_id[mark.partId]]
    ]
    annotation_shapes = {}
    for layer, suffix, records in (
        ("INTERIORS", "interior", elevation.interiors),
        ("GLASS_MARKS", "glass", elevation.glassMarks),
    ):
        annotation_shapes[layer] = [
            HlrShape(
                id=f"{part.id}#{suffix}",
                polygon=rect_polygon(part.x, part.z, part.width, part.height),
                front=part.front,
                drop_hidden=True,
                lines=tuple(((line.x1, line.z1), (line.x2, line.z2)) for line in record.lines),
                opaque=False,
                outlined=False,
            )
            for record in records
            for part in [by_id[record.partId]]
        ]
    pull_shapes = []
    pull_sources = {}
    for pull in elevation.pulls:
        part = by_id[pull.partId]
        for outline in pull.outlines:
            points, sources = flatten_outline(outline)
            shape_id = f"{part.id}#pull{len(pull_shapes)}"
            pull_sources[shape_id] = sources
            pull_shapes.append(HlrShape(
                id=shape_id,
                polygon=rect_polygon(part.x, part.z, part.width, part.height),
                front=part.front,
                drop_hidden=True,
                lines=tuple(zip(points, points[1:] + points[:1])),
                opaque=False,
                outlined=False,
            ))
    lines = hidden_line_removal(
        shapes + detail_shapes + swing_shapes + pull_shapes
        + [shape for group in annotation_shapes.values() for shape in group]
    )
    for part in parts:
        visible, hidden = lines[part.id]
        sources = outlines[part.id][1] if part.outline is not None else []
        visible, visible_arcs = rejoin_arcs(visible, sources)
        hidden, hidden_arcs = rejoin_arcs(hidden, sources)
        write_lines_to_layer(doc, KIND_LAYERS[part.kind], visible)
        write_lines_to_layer(doc, "HIDDEN", hidden)
        write_arcs_to_layer(doc, KIND_LAYERS[part.kind], visible_arcs)
        write_arcs_to_layer(doc, "HIDDEN", hidden_arcs)

    for shape in detail_shapes:
        write_lines_to_layer(doc, "DOOR_DETAILS", lines[shape.id][0])
    for shape in swing_shapes:
        write_lines_to_layer(doc, "SWING_MARKS", lines[shape.id][0])
    for layer, group in annotation_shapes.items():
        for shape in group:
            write_lines_to_layer(doc, layer, lines[shape.id][0])
    for shape in pull_shapes:
        visible, arcs = rejoin_arcs(lines[shape.id][0], pull_sources[shape.id])
        write_lines_to_layer(doc, "PULLS", visible)
        write_arcs_to_layer(doc, "PULLS", arcs)
    _add_tags(modelspace, elevation.doorDetails, by_id, plot_scale)
    _add_interior_labels(modelspace, elevation.interiors, plot_scale)

    regions = visible_regions(shapes, {part.id for part in parts if part.kind in HATCHED})
    for part in parts:
        if part.id in regions:
            _add_hatch(modelspace, KIND_LAYERS[part.kind], regions[part.id])

    add_dimensions(modelspace, elevation.dimensions)
    add_marks(modelspace, elevation.marks, plot_scale)

    # The title sits under the lowest horizontal dimension line or moved text (SPEC-43, 43.1, 43.2); with none, where it always has.
    low = min([
        0.0,
        *(dimension.at for dimension in elevation.dimensions if dimension.orientation == "horizontal"),
        *(dimension.textZ for dimension in elevation.dimensions
          if dimension.orientation == "horizontal" and dimension.textZ is not None),
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

    add_part_numbers(modelspace, elevation.partNumbers)
    frame_drawing(doc, plot_scale)
    doc.update_extents()
    return doc


def build_elevation_dxf(
    elevation: PayloadElevation, room: PayloadRoom, plot_scale: float = DEFAULT_PLOT_SCALE,
) -> bytes:
    return doc_to_bytes(make_elevation_doc(elevation, room, plot_scale))
