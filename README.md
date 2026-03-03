# Cabinetry Designer — Geometry Engine

Python engine that receives fully-resolved parametric room data and deterministically generates 2D DXF drawings and manufacturing reports. No AI-generated geometry — everything is rule-based and reproducible.

## Tech Stack

- **Python 3.10+**
- **ezdxf** — DXF file generation
- **Shapely** — 2D geometry operations (HLR clipping)
- **Pydantic** — Data validation / models
- **NumPy** — Math utilities

## Getting Started

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Test CLI manually
echo '{"room_id":"test","name":"Kitchen","floor_to_ceiling":96,"walls":[],"objects":[]}' | python -m src generate
```

## Architecture

```
src/
├── cli.py                  # CLI entry: stdin JSON → stdout JSON
├── models/                 # Pydantic schemas (room, cabinet, geometry primitives)
├── parametric/             # Expand resolved params → 3D box primitives
│   └── cabinet_builder.py  # Case, doors, drawers, shelves, toe kick
├── projection/             # 2D projections from 3D primitives
│   ├── floorplan.py        # Top-down XY projection
│   ├── elevation.py        # Wall-aligned front projection
│   ├── hlr.py              # Hidden line removal (depth-sort + Shapely clip)
│   └── section.py          # Cut-plane section views (stub)
├── dxf/                    # DXF file writers using ezdxf
│   ├── writer.py           # Layer management, line writing
│   ├── floorplan_dxf.py
│   └── elevation_dxf.py
├── reports/                # Manufacturing report generators
│   ├── shipping_list.py
│   ├── door_list.py
│   ├── drawer_front_list.py
│   └── drawer_box_list.py
└── utils/                  # Math helpers, constants
```

## Pipeline

1. **Input**: Resolved room JSON (all params filled, no nulls) from Node backend
2. **Parametric Expansion**: Each cabinet → list of axis-aligned BoxPrimitives
3. **Floorplan Projection**: Top-down onto XY plane → layered lines
4. **Elevation Projection**: Per-wall front projection → HLR → visible/hidden lines
5. **DXF Generation**: Lines written to ezdxf with proper layers and linetypes
6. **Reports**: Walk primitives to produce shipping, door, drawer front, drawer box lists
7. **Output**: JSON with `dxf_base64` + `reports` on stdout

## HLR Strategy

For axis-aligned cabinet boxes on wall elevations:
1. Front-project each box onto XZ plane (discard depth Y)
2. Depth-sort front-to-back
3. For each box, clip its projected edges against the union of all in-front faces (Shapely `difference()`)
4. Visible → solid DXF lines, hidden → dashed lines

O(n²) in box count per wall, fast for typical cabinet counts (~5-20 per wall).
