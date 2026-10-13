"""Drawing payload v1 models (SPEC-40)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import Polygon

from .arcs import flatten_outline


Bulge = Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]


class PayloadRoom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str


class PayloadHole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    z: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class PayloadLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x1: float
    z1: float
    x2: float
    z2: float


class PayloadPartNumber(BaseModel):
    """A pre-positioned part badge (SPEC-50.13), centred at x/z in wall inches.

    Width and height are already scaled to drawing inches by the designer;
    an optional leader connects the badge to its part or anchor.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    text: str = Field(min_length=1)
    x: float
    z: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    leader: PayloadLine | None = None


class PayloadPart(BaseModel):
    """An elevation part, optionally outlined by absolute (x, z[, bulge]) points.

    `outline` closes implicitly, ignores holes, and uses the required x/z/width/height rectangle
    as its bounds. Bulge belongs to the next segment (including closure), is
    tan(sweep / 4), positive counter-clockwise, and rounded to six places.
    Omitted bulges are straight; arcs are at most 180 degrees.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal[
        "cabinet", "face", "filler", "end_panel", "panel", "frame", "shelf",
        "toe_kick", "furniture_base", "countertop", "top_mold", "crown",
        "light_rail", "light_trough", "bottom_cap", "corbels",
        "wall_end_panel", "opening", "casing", "soffit", "recess", "projection", "wing_wall",
        "section", "profile",
    ]
    runId: str | None = None
    x: float
    z: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    back: float
    front: float
    coversBoxEdges: bool
    holes: list[PayloadHole] = []
    outline: list[tuple[float, float] | tuple[float, float, Bulge]] | None = None
    lines: list[PayloadLine] = []
    profileId: str | None = None
    opaque: bool = True
    openEdges: list[Literal["left", "right", "top", "bottom"]] = []

    @model_validator(mode="after")
    def check_outline(self):
        if self.outline is None:
            return self
        if len(self.outline) < 3:
            raise ValueError("Part outline must have at least 3 points")
        self.outline = [
            (point[0], point[1], round(point[2], 6)) if len(point) == 3 else point
            for point in self.outline
        ]
        flattened, _ = flatten_outline(self.outline)
        tolerance = 1e-6
        for x, z in flattened:
            if not (
                self.x - tolerance <= x <= self.x + self.width + tolerance
                and self.z - tolerance <= z <= self.z + self.height + tolerance
            ):
                raise ValueError("Part outline points must be inside the part's bounds")
        if Polygon(flattened).area <= 0:
            raise ValueError("Part outline must have non-zero area")
        return self


class PayloadDimension(BaseModel):
    """One linear dimension (SPEC-43): from start to end along the elevation, extension lines from
    `base`, the dimension line at `at`, its text as the designer formats it."""

    model_config = ConfigDict(extra="forbid")

    row: str = Field(min_length=1)
    # Vertical dimensions run up the wall (SPEC-43.2): start/end are heights, base/at are x.
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    kind: str = Field(min_length=1)
    start: float
    end: float
    base: float
    at: float
    text: str = Field(min_length=1)
    # Where the text's middle goes when it doesn't fit between the ticks (SPEC-43.1); None = on the line.
    textX: float | None = None
    textZ: float | None = None
    # Where the extension line at start / end begins (SPEC-43.3); None = base.
    startBase: float | None = None
    endBase: float | None = None


class PayloadMark(BaseModel):
    """A centreline mark (SPEC-43.3): a centre line at `x` from `bottom` to `top`,
    its label's middle at `textX`/`textZ`."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["centerline"]
    x: float
    bottom: float
    top: float
    text: str = Field(min_length=1)
    textX: float
    textZ: float


class PayloadDoorDetail(BaseModel):
    """A part's frame openings (5-piece) or molding rectangles (Slab AM) (SPEC-46.4)
    and its profile lines (SPEC-50) and miter segments (SPEC-50.4), drawn at its
    part's depth on DOOR_DETAILS with hidden segments dropped;
    its style tag on DOOR_TAGS (none = no tag)."""

    model_config = ConfigDict(extra="forbid")

    partId: str = Field(min_length=1)
    openings: list[PayloadHole] = []
    profileLines: list[PayloadHole] = []
    miters: list[PayloadLine] = []
    tag: str | None = Field(default=None, min_length=1)


class PayloadElevation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    letter: str = Field(min_length=1)
    wallId: str
    side: Literal["front", "back"]
    title: str
    wallLabel: str
    length: float = Field(gt=0)
    height: float = Field(gt=0)
    parts: list[PayloadPart] = []
    dimensions: list[PayloadDimension] = []
    marks: list[PayloadMark] = []
    # Door details per part (SPEC-46.4); each names a part in this elevation.
    doorDetails: list[PayloadDoorDetail] = []
    # Pre-positioned badges in drawing inches (SPEC-50.13), always exported.
    partNumbers: list[PayloadPartNumber] = []

    @model_validator(mode="after")
    def check_door_detail_parts(self):
        part_ids = {part.id for part in self.parts}
        unknown_ids = sorted({detail.partId for detail in self.doorDetails} - part_ids)
        if unknown_ids:
            raise ValueError(f"Door details name unknown part ids: {', '.join(unknown_ids)}")
        return self


class PayloadPlanPart(BaseModel):
    """One outline in plan (SPEC-44), in plan inches with y up. Walls are joined and voids cut out of them."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal[
        "wall", "void", "opening", "casing", "recess", "soffit", "cabinet", "face",
        "filler", "end_panel", "panel", "frame", "shelf", "wall_end_panel", "countertop",
    ]
    runId: str | None = None
    points: list[tuple[float, float]] = Field(min_length=2)
    closed: bool = True
    dashed: bool = False
    # How high its top is (SPEC-44.1). A part with a top hides the lines of lower parts under it; None is drawn over all.
    top: float | None = None


class PayloadPlanDimension(BaseModel):
    """One aligned dimension in plan (SPEC-45), plan inches with y up: measured from start to end,
    extension lines from those points, the dimension line `offset` to the left of start→end (negative: right)."""

    model_config = ConfigDict(extra="forbid")

    row: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    start: tuple[float, float]
    end: tuple[float, float]
    offset: float
    text: str = Field(min_length=1)
    # Where the text's middle goes when it doesn't fit between the ticks; None = on the line.
    textAt: tuple[float, float] | None = None


class PayloadPlanMark(BaseModel):
    """An elevation marker or a label in plan (SPEC-45.1), plan inches with y up. Geometry draws the symbol
    at its paper size; the designer places it."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["elevation", "label"]
    at: tuple[float, float]
    text: str = Field(min_length=1)
    # An elevation marker's flag points this way, at the wall face it looks at (a unit vector).
    direction: tuple[float, float] | None = None
    # A label's angle, degrees counter-clockwise.
    rotation: float = 0


class PayloadPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[PayloadPlanPart] = []
    # Wall lengths and the rows along each face (SPEC-45); depths and clearances in 45.2.
    dimensions: list[PayloadPlanDimension] = []
    # Elevation markers and door, window and recess labels (SPEC-45.1).
    marks: list[PayloadPlanMark] = []


class DrawingPayload(BaseModel):
    """Drawing request; paperSize selects PDF paper, defaulting to letter when omitted."""

    model_config = ConfigDict(extra="forbid")

    payloadVersion: Literal[1]
    units: Literal["in"]
    room: PayloadRoom
    elevations: list[PayloadElevation]
    # Drawing scale (SPEC-43): 24 is 1/2" = 1'-0". None draws at 24, so a payload without it round-trips.
    plotScale: float | None = Field(default=None, gt=0)
    paperSize: Literal["letter", "ledger", "archD"] | None = None
    # The room in plan (SPEC-44). None draws no plan.dxf, so a payload without it round-trips.
    plan: PayloadPlan | None = None
