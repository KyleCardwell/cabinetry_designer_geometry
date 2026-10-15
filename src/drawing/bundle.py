"""Validate a drawing payload and bundle its DXFs and PDF."""

import base64
import io
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from src.dxf.writer import doc_to_bytes

from .dimensions import DEFAULT_PLOT_SCALE
from .elevation_dxf import make_elevation_doc
from .models import DrawingPayload
from .pdf import render_pdf
from .plan_dxf import make_plan_doc


def draw(payload: dict) -> dict:
    model = DrawingPayload.model_validate(payload)
    plot_scale = model.plotScale or DEFAULT_PLOT_SCALE
    files = []
    docs = []
    if model.plan is not None:
        doc = make_plan_doc(model.plan, model.room, plot_scale)
        files.append(("plan.dxf", doc_to_bytes(doc)))
        docs.append(doc)
    for elevation in model.elevations:
        doc = make_elevation_doc(elevation, model.room, plot_scale)
        files.append((f"elevation-{elevation.letter}.dxf", doc_to_bytes(doc)))
        docs.append(doc)
    if docs:
        files.append(("drawings.pdf", render_pdf(
            docs, model.paperSize or "letter", plot_scale, revision=model.room.revision,
        )))
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in [("payload.json", model.model_dump_json(indent=2, exclude_defaults=True)), *files]:
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, content)

    return {
        "payloadVersion": 1,
        "files": [name for name, _ in files],
        "zip_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
    }
