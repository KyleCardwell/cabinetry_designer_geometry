# Cabinetry Designer — Geometry Engine

Python renderer for drawing payload v1 built by the designer's `toDrawingPayload` function. The designer supplies the wall face dimensions in inches; geometry draws one DXF per elevation and bundles them into a zip with `payload.json`.

## Getting Started

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest
.venv/bin/python -m src draw < tests/fixtures/g1_payload.json
```

## Drawing Command

`draw` is the only CLI command. It reads a drawing payload v1 as JSON from stdin and writes JSON to stdout:

```json
{
  "payloadVersion": 1,
  "files": ["elevation-A.dxf", "elevation-B.dxf", "elevation-C.dxf", "elevation-D.dxf"],
  "zip_base64": "..."
}
```

Decode `zip_base64` to obtain the zip. It contains `payload.json` first, followed by one `elevation-<letter>.dxf` per elevation in payload order. Each DXF shows the wall face rectangle, elevation title, wall label, and room name, with units set to inches.

Payload validation errors are written to stderr as JSON with exit code 2. Other errors use exit code 1.

## Architecture

```text
src/
├── cli.py                  # draw: stdin JSON → stdout JSON
├── drawing/
│   ├── models.py           # Strict drawing payload v1 models
│   ├── elevation_dxf.py    # DXF per elevation
│   └── bundle.py           # Payload validation and zip assembly
├── dxf/writer.py           # DXF document, layers, and units
├── projection/hlr.py       # hidden-line removal: nearer parts hide farther ones; hidden edges dashed on HIDDEN (SPEC-41)
├── models/geometry.py      # Geometry primitives used by hidden-line removal
└── utils/                  # Math helpers and constants
```

Geometry renders the dimensions supplied by the designer. Hidden-line removal and the shared DXF writer remain available for round 41.

## Layers

| Part kind | Visible layer |
|---|---|
| `cabinet` | `CABINETS` |
| `face` | `FACES` |
| `filler` | `FILLERS` |
| `end_panel`, `panel` | `PANELS` |
| `frame` | `FRAMES` |
| `shelf` | `SHELVES` |
| `countertop` | `COUNTERTOPS` |
| `toe_kick`, `top_mold`, `crown`, `light_rail`, `light_trough`, `bottom_cap`, `corbels` | `MOLDINGS` |

A part's `lines` are detail lines drawn inside it and hidden like its outline; toe kicks, top molds and crowns are never dashed (their hidden edges are left out); `profileId` is accepted and ignored until profiles exist (SPEC-42).

Hidden segments use the dashed `HIDDEN` layer.
