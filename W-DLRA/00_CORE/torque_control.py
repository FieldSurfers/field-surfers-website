"""Torque control for rotating unstable manifold states toward lower entropy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class TorqueConfig:
    rotation_gain: float = 0.25
    entropy_dampening: float = 0.40


def apply_torque(
    state_vector: Sequence[float],
    reference_signal: Sequence[float],
    entropy: float,
    config: TorqueConfig = TorqueConfig(),
) -> list[float]:
    """Apply a geometric pull toward reference while dampening by entropy.

    This function is intentionally simple and interpretable:
      rotated = state - gain * entropy_dampening_factor * (state - reference)
    """
    if len(state_vector) != len(reference_signal):
        raise ValueError("state_vector and reference_signal must have equal dimensions")

    dampening = 1.0 - min(max(entropy, 0.0), 1.0) * config.entropy_dampening
    step = config.rotation_gain * dampening

    return [
        current - step * (current - target)
        for current, target in zip(state_vector, reference_signal)
    ]
