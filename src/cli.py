"""
CLI entry point for the geometry engine.

Usage:
    python -m src draw < drawing-payload.json

Reads JSON from stdin, outputs JSON to stdout:
    draw: { "payloadVersion": 1, "files": [...], "zip_base64": "..." }
"""

from __future__ import annotations
import sys
import json

from pydantic import ValidationError

from .drawing.bundle import draw


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python -m src draw"}), file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "draw":
        try:
            input_data = json.load(sys.stdin)
            json.dump(draw(input_data), sys.stdout)
        except ValidationError as e:
            print(json.dumps({
                "error": "Invalid drawing payload",
                "details": json.loads(e.json(include_url=False)),
            }), file=sys.stderr)
            sys.exit(2)
        except Exception as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps({"error": f"Unknown command: {command}"}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
