#!/usr/bin/env python3
"""Flight Controller: watches stream input and routes files through manifold/torque/veto."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

STREAM_DIR = Path("W-DLRA/01_FIELD/stream")
GLITCH_DIR = Path("W-DLRA/01_FIELD/glitch_log")
LIFT_DIR = Path("W-DLRA/02_WINGZ/lift_protocols")


@dataclass
class EntropyResult:
    score: float
    label: str


class EngineAdapters:
    """Try project modules first; fallback to local deterministic behavior."""

    def __init__(self) -> None:
        self.manifold_engine = self._optional_import("manifold_engine")
        self.torque_control = self._optional_import("torque_control")
        self.hard_veto = self._optional_import("hard_veto")

    @staticmethod
    def _optional_import(name: str) -> Any | None:
        try:
            module = __import__(name)
            return module
        except Exception:
            return None

    def entropy(self, content: str) -> EntropyResult:
        if self.manifold_engine:
            candidate_methods: list[tuple[Any, str]] = [
                (self.manifold_engine, "calculate_entropy"),
                (self.manifold_engine, "entropy_score"),
                (self.manifold_engine, "measure_entropy"),
                (self.manifold_engine, "run"),
            ]
            for owner, method_name in candidate_methods:
                method = getattr(owner, method_name, None)
                if callable(method):
                    value = method(content)
                    return self._coerce_entropy(value)

        # Fallback heuristic entropy score [0, 1]
        words = re.findall(r"\b\w+\b", content.lower())
        token_count = len(words) or 1
        unique_ratio = len(set(words)) / token_count
        surreal_tokens = {
            "dreams", "purple", "clouds", "fly", "wings", "magic", "ether",
            "telepathy", "hallucination", "becomes", "eat"
        }
        surreal_hits = sum(1 for w in words if w in surreal_tokens)
        surreal_ratio = surreal_hits / token_count
        score = min(1.0, 0.55 * unique_ratio + 0.45 * surreal_ratio)
        label = "HIGH" if score >= 0.45 else "LOW"
        return EntropyResult(score=score, label=label)

    @staticmethod
    def _coerce_entropy(value: Any) -> EntropyResult:
        if isinstance(value, dict):
            score = float(value.get("score", value.get("entropy", 0.0)))
            label = str(value.get("label") or ("HIGH" if score >= 0.45 else "LOW"))
            return EntropyResult(score=score, label=label.upper())
        if isinstance(value, (float, int)):
            score = float(value)
            return EntropyResult(score=score, label="HIGH" if score >= 0.45 else "LOW")
        if isinstance(value, str):
            parsed = float(value)
            return EntropyResult(score=parsed, label="HIGH" if parsed >= 0.45 else "LOW")
        raise TypeError(f"Unsupported entropy value: {type(value)}")

    def torque(self, content: str) -> str:
        if self.torque_control:
            candidate_methods: list[tuple[Any, str]] = [
                (self.torque_control, "rotate"),
                (self.torque_control, "rewrite"),
                (self.torque_control, "compress"),
                (self.torque_control, "run"),
            ]
            for owner, method_name in candidate_methods:
                method = getattr(owner, method_name, None)
                if callable(method):
                    result = method(content)
                    if isinstance(result, str):
                        return result
                    if isinstance(result, dict):
                        return str(result.get("content", result.get("text", content)))
        # fallback: compress repeated whitespace and keep first 24 words
        words = re.findall(r"\S+", content)
        rotated = " ".join(words[:24]).strip()
        return rotated

    def veto(self, content: str) -> tuple[bool, str]:
        if self.hard_veto:
            candidate_methods: list[tuple[Any, str]] = [
                (self.hard_veto, "evaluate"),
                (self.hard_veto, "check"),
                (self.hard_veto, "is_grounded"),
                (self.hard_veto, "run"),
            ]
            for owner, method_name in candidate_methods:
                method = getattr(owner, method_name, None)
                if callable(method):
                    result = method(content)
                    if isinstance(result, bool):
                        return result, "module_boolean"
                    if isinstance(result, dict):
                        grounded = bool(result.get("grounded", result.get("passed", False)))
                        reason = str(result.get("reason", "module_dict"))
                        return grounded, reason
        # fallback groundedness heuristic
        lowered = content.lower()
        nonsense_flags = [
            "data becomes purple",
            "eat the clouds",
            "wings are made of dreams",
        ]
        for flag in nonsense_flags:
            if flag in lowered:
                return False, f"ungrounded_phrase:{flag}"
        concrete_terms = {"device", "sensor", "mode", "input", "output", "log", "test", "system", "file"}
        words = set(re.findall(r"\b\w+\b", lowered))
        grounded = len(words.intersection(concrete_terms)) >= 1
        return grounded, "fallback_groundedness"


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

    grounded, reason = adapters.veto(final_content)

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
            "grounded": grounded,
            "veto_reason": reason,
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
