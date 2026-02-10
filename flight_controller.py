#!/usr/bin/env python3
"""Flight Controller: watches stream input and routes files through manifold/torque/veto."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STREAM_DIR = Path("W-DLRA/01_FIELD/stream")
GLITCH_DIR = Path("W-DLRA/01_FIELD/glitch_log")
LIFT_DIR = Path("W-DLRA/02_WINGZ/lift_protocols")
CORE_DIR = Path("W-DLRA/00_CORE").resolve()
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from text_adapters import entropy_score, grounding_check, rotate_text


@dataclass
class EntropyResult:
    score: float
    label: str
    details: dict[str, Any]


class EngineAdapters:
    """Use deterministic core adapters for entropy, torque, and grounding checks."""

    def entropy(self, content: str) -> EntropyResult:
        result = entropy_score(content)
        return EntropyResult(
            score=float(result["score"]),
            label=str(result["label"]),
            details=dict(result.get("details", {})),
        )

    def torque(self, content: str) -> str:
        return rotate_text(content)

    def veto(self, content: str) -> tuple[bool, str, dict[str, Any]]:
        result = grounding_check(content)
        return bool(result["grounded"]), str(result["reason"]), dict(result.get("evidence", {}))


def ensure_dirs() -> None:
    STREAM_DIR.mkdir(parents=True, exist_ok=True)
    GLITCH_DIR.mkdir(parents=True, exist_ok=True)
    LIFT_DIR.mkdir(parents=True, exist_ok=True)


def process_file(path: Path, adapters: EngineAdapters) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    entropy = adapters.entropy(content)

    rotated_content = None
    final_content = content
    if entropy.label == "HIGH":
        rotated_content = adapters.torque(content)
        final_content = rotated_content

    grounded, reason, evidence = adapters.veto(final_content)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if entropy.label == "LOW" and grounded:
        destination = LIFT_DIR / path.name
        shutil.move(str(path), destination)
        if rotated_content is not None:
            destination.write_text(rotated_content, encoding="utf-8")
        status = "SUCCESS_LIFTED"
    else:
        moved_input = GLITCH_DIR / path.name
        shutil.move(str(path), moved_input)
        report_path = GLITCH_DIR / f"{path.stem}.{ts}.failure.json"
        report = {
            "file": path.name,
            "status": "VETO_FAIL" if not grounded else "ENTROPY_HIGH",
            "entropy_score": entropy.score,
            "entropy_label": entropy.label,
            "entropy_details": entropy.details,
            "grounded": grounded,
            "veto_reason": reason,
            "grounding_evidence": evidence,
            "torqued": rotated_content is not None,
            "torque_output_preview": (rotated_content or "")[:240],
            "timestamp_utc": ts,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        status = report["status"]

    return {
        "file": path.name,
        "entropy_score": entropy.score,
        "entropy_label": entropy.label,
        "grounded": grounded,
        "veto_reason": reason,
        "status": status,
    }


def stream_files() -> list[Path]:
    return sorted([p for p in STREAM_DIR.iterdir() if p.is_file() and not p.name.startswith(".")])


def run_loop(poll_seconds: float = 1.0, once: bool = False, max_iterations: int | None = None) -> None:
    ensure_dirs()
    adapters = EngineAdapters()
    iterations = 0
    print(f"[flight-controller] watching: {STREAM_DIR}")

    while True:
        files = stream_files()
        if files:
            for f in files:
                result = process_file(f, adapters)
                print(json.dumps(result))

            if once:
                break

        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break

        time.sleep(poll_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Field Surfer Flight Controller")
    parser.add_argument("--once", action="store_true", help="Process current files and exit")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--max-iterations", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_loop(poll_seconds=args.poll_seconds, once=args.once, max_iterations=args.max_iterations)
