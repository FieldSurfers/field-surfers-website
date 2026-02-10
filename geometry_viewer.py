#!/usr/bin/env python3
"""CLI for generating W-DLRA thinking-geometry artifacts from observable traces."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _load_thinking_geometry_module():
    module_path = Path("W-DLRA/00_CORE/thinking_geometry.py")
    spec = importlib.util.spec_from_file_location("thinking_geometry", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate thinking-geometry graph artifacts.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("W-DLRA/01_FIELD/stream/test_geometry.txt"),
        help="Path to text/JSON/JSONL trace with prompt + response (+optional events).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("W-DLRA/01_FIELD/geometry"),
        help="Destination folder for graph.json, graph.svg, and metrics.json.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single generation pass and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"error: input trace does not exist: {args.input}")
        return 2

    module = _load_thinking_geometry_module()
    try:
        graph_json, svg, metrics = module.generate_geometry(args.input, args.output_dir)
    except module.TraceParseError as exc:
        print(f"error: {exc}")
        return 1

    print("Generated geometry artifacts:")
    print(f"- {graph_json}")
    print(f"- {svg}")
    print(f"- {metrics}")

    if args.once:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
