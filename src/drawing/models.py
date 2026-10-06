"""Drawing payload v1 models (SPEC-40)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class PayloadPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal[
        "cabinet", "face", "filler", "end_panel", "panel", "frame", "shelf",
        "toe_kick", "countertop", "top_mold", "crown",
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
    lines: list[PayloadLine] = []
    profileId: str | None = None
    opaque: bool = True
    openEdges: list[Literal["left", "right", "top", "bottom"]] = []


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


class DrawingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payloadVersion: Literal[1]
    units: Literal["in"]
    room: PayloadRoom
    elevations: list[PayloadElevation]
    # Drawing scale (SPEC-43): 24 is 1/2" = 1'-0". None draws at 24, so a payload without it round-trips.
    plotScale: float | None = Field(default=None, gt=0)
