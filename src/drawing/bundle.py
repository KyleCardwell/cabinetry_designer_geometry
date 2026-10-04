"""Validate a drawing payload and bundle its elevation DXFs."""

import base64
import io
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .elevation_dxf import build_elevation_dxf
from .models import DrawingPayload


def draw(payload: dict) -> dict:
    model = DrawingPayload.model_validate(payload)
    elevations = [
        (f"elevation-{elevation.letter}.dxf", build_elevation_dxf(elevation, model.room))
        for elevation in model.elevations
    ]
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in [("payload.json", model.model_dump_json(indent=2)), *elevations]:
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, content)

    return {
        "payloadVersion": 1,
        "files": [name for name, _ in elevations],
        "zip_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
    }
