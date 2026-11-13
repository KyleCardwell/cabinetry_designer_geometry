"""Vector PDF pages from the same framed documents as the DXFs (SPEC-50.15)."""

import io
import logging

from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration, LineweightPolicy
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.document import Drawing
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from src.dxf.writer import TEXT_FAMILY


PAPER_SIZES = {"letter": (8.5, 11), "ledger": (11, 17), "archD": (24, 36)}
PRINTER_MARGIN = 0.25
logger = logging.getLogger(__name__)


def fit_page(frame_w: float, frame_h: float, paper: str, plot_scale: float) -> tuple:
    """Prefer landscape, then portrait at plot scale; otherwise shrink the better fit."""
    short, long = PAPER_SIZES[paper]
    orientations = [(long, short), (short, long)]
    required = [
        max(frame_w / (w - 2 * PRINTER_MARGIN), frame_h / (h - 2 * PRINTER_MARGIN))
        for w, h in orientations
    ]
    for (w, h), scale in zip(orientations, required):
        if scale <= plot_scale:
            return w, h, plot_scale, True
    index = 0 if required[0] <= required[1] else 1
    w, h = orientations[index]
    return w, h, required[index], False


def scale_label(plot_scale: float, to_scale: bool) -> str:
    """Architectural scale note, or a ratio for scales outside the designer's table."""
    if not to_scale:
        return "NOT TO SCALE"
    architectural = {12: '1', 16: '3/4', 24: '1/2', 32: '3/8', 48: '1/4'}
    if plot_scale in architectural:
        return f'SCALE {architectural[plot_scale]}" = 1\'-0"'
    return f"SCALE 1:{plot_scale:g}"


def render_pdf(docs: list[Drawing], paper: str, plot_scale: float, revision: str | None = None) -> bytes:
    """Render one page per document; log scale notes and nonblank revision labels."""
    buffer = io.BytesIO()
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    note_family = next(
        (family for family in (TEXT_FAMILY, "Liberation Sans", "Arimo") if family in available_fonts),
        "sans-serif",
    )
    config = Configuration(
        background_policy=BackgroundPolicy.WHITE,
        lineweight_policy=LineweightPolicy.ABSOLUTE,
        # ezdxf resolves millimetres; matplotlib's stroke widths are in points.
        lineweight_scaling=72 / 25.4,
        min_lineweight=0,
    )
    with PdfPages(buffer, metadata={"CreationDate": None, "ModDate": None}) as pdf:
        for page, doc in enumerate(docs, start=1):
            low, high = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
            w, h, scale, to_scale = fit_page(high[0] - low[0], high[1] - low[1], paper, plot_scale)
            cx, cy = (low[0] + high[0]) / 2, (low[1] + high[1]) / 2
            fig = Figure(figsize=(w, h), facecolor="white")
            ax = fig.add_axes((0, 0, 1, 1))
            ax.set_axis_off()
            backend = MatplotlibBackend(ax, adjust_figure=False)
            ax.set_xlim(cx - w * scale / 2, cx + w * scale / 2)
            ax.set_ylim(cy - h * scale / 2, cy + h * scale / 2)
            Frontend(RenderContext(doc), backend, config=config).draw_layout(
                doc.modelspace(), finalize=False,
            )
            label = scale_label(plot_scale, to_scale)
            fig.text(
                w - 3 / 16, 3 / 16, label,
                transform=fig.dpi_scale_trans, ha="right", va="bottom",
                family=note_family,
                fontsize=72 / 8, color="black",
            )
            logger.info("PDF page %d scale note: %s", page, label)
            if revision and revision.strip():
                fig.text(
                    3 / 16, 3 / 16, revision,
                    transform=fig.dpi_scale_trans, ha="left", va="bottom",
                    family=note_family, fontsize=9, color="black",
                )
                logger.info("PDF page %d revision: %s", page, revision)
            pdf.savefig(fig, bbox_inches=None)
            fig.clear()
    return buffer.getvalue()
