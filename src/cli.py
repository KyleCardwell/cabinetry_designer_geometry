"""
CLI entry point for the geometry engine.

Usage:
    echo '{"room_id": "...", ...}' | python -m src.cli generate

Reads resolved room JSON from stdin, outputs JSON to stdout:
    { "dxf_base64": "...", "reports": { ... } }
"""

from __future__ import annotations
import sys
import json
import base64

from .models.room import ResolvedRoom
from .parametric.cabinet_builder import expand_cabinet
from .projection.floorplan import generate_floorplan
from .projection.elevation import generate_all_elevations
from .dxf.floorplan_dxf import build_floorplan_dxf
from .dxf.elevation_dxf import build_elevation_dxf
from .reports.shipping_list import build_shipping_list
from .reports.door_list import build_door_list
from .reports.drawer_front_list import build_drawer_front_list
from .reports.drawer_box_list import build_drawer_box_list


def generate(room_data: dict) -> dict:
    """
    Main generation pipeline.

    1. Parse resolved room JSON
    2. Expand all objects into box primitives
    3. Generate floorplan projection
    4. Generate wall elevations with HLR
    5. Build DXF files
    6. Build reports
    7. Return combined result
    """
    room = ResolvedRoom(**room_data)

    # Step 1: Parametric expansion
    object_boxes: dict[str, list] = {}
    for obj in room.objects:
        object_boxes[obj.object_id] = expand_cabinet(obj)

    # Step 2: Floorplan
    floorplan_layers = generate_floorplan(room, object_boxes)

    # Step 3: Elevations with HLR
    elevations = generate_all_elevations(room, object_boxes)

    # Step 4: Build DXF — combine floorplan + elevations into one file
    floorplan_bytes = build_floorplan_dxf(floorplan_layers, room_name=room.name)
    elevation_bytes = build_elevation_dxf(elevations, room_name=room.name)

    # For POC, return the floorplan DXF as the primary output.
    # Elevation DXF could be a separate file or combined later.
    # We'll combine by using the floorplan as the main DXF for now.
    dxf_b64 = base64.b64encode(floorplan_bytes).decode("ascii")

    # Step 5: Reports
    reports = {
        "shipping_list": build_shipping_list(room.objects),
        "door_list": build_door_list(room.objects),
        "drawer_front_list": build_drawer_front_list(room.objects),
        "drawer_box_list": build_drawer_box_list(room.objects),
    }

    return {
        "dxf_base64": dxf_b64,
        "elevation_dxf_base64": base64.b64encode(elevation_bytes).decode("ascii"),
        "reports": reports,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python -m src.cli generate"}), file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "generate":
        try:
            input_data = json.load(sys.stdin)
            result = generate(input_data)
            json.dump(result, sys.stdout)
        except Exception as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps({"error": f"Unknown command: {command}"}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
