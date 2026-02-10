"""Wingz Resonant Manifold (WRM) state evaluator.

Pseudo-code + executable skeleton for tracking entropy as a state dimension.
Fail-loud behavior is intentional: unstable manifold states raise exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import dist
from typing import Iterable, Mapping, Sequence


class EntropyDriftError(RuntimeError):
    """Raised when a state drifts beyond reference tolerances."""


@dataclass(frozen=True)
class ManifoldState:
    """State vector sampled from Loop A and measured by Loop B."""

    vector: Sequence[float]
    entropy: float
    coherence: float
    timestamp: float


class ResonantManifoldEngine:
    """Tracks entropy as a first-class state dimension.

    Design intent (pseudo-flow):
        ingest(state) -> compare_to_reference() -> veto_or_rotate() -> accept/reject

    A state is rejected when:
      1) Euclidean drift from reference signal exceeds `max_drift`, OR
      2) entropy exceeds `max_entropy`, OR
      3) coherence drops below `min_coherence`.
    """

    def __init__(
        self,
        reference_signal: Sequence[float],
        *,
        max_drift: float = 1.5,
        max_entropy: float = 0.45,
        min_coherence: float = 0.70,
    ) -> None:
        self.reference_signal = tuple(reference_signal)
        self.max_drift = max_drift
        self.max_entropy = max_entropy
        self.min_coherence = min_coherence
        self.history: list[ManifoldState] = []

    def evaluate(self, state: ManifoldState) -> Mapping[str, float | bool]:
        """Evaluate incoming state against WRM constraints.

        Returns metrics only if state remains grounded in manifold limits.
        Raises EntropyDriftError on any critical divergence (fail loud).
        """
        if len(state.vector) != len(self.reference_signal):
            raise EntropyDriftError("State vector dimensionality mismatch.")

        drift = dist(state.vector, self.reference_signal)

        if drift > self.max_drift:
            raise EntropyDriftError(
                f"State rejected: drift={drift:.3f} exceeds max_drift={self.max_drift:.3f}."
            )

        if state.entropy > self.max_entropy:
            raise EntropyDriftError(
                f"State rejected: entropy={state.entropy:.3f} exceeds max_entropy={self.max_entropy:.3f}."
            )

        if state.coherence < self.min_coherence:
            raise EntropyDriftError(
                f"State rejected: coherence={state.coherence:.3f} below min_coherence={self.min_coherence:.3f}."
            )

        self.history.append(state)
        return {
            "accepted": True,
            "drift": drift,
            "entropy": state.entropy,
            "coherence": state.coherence,
        }

    def latest_entropy_trend(self, window: int = 5) -> float:
        """Compute simple entropy trend slope proxy over recent states."""
        if window <= 1 or len(self.history) < 2:
            return 0.0

        recent: Iterable[ManifoldState] = self.history[-window:]
        entropies = [s.entropy for s in recent]
        return entropies[-1] - entropies[0]
