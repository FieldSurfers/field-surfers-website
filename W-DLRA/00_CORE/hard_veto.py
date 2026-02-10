"""Hard-Veto reality constraint.

Any Bloom intended for /02_WINGZ must pass external grounding checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


class GroundingVetoError(RuntimeError):
    """Raised when a result cannot be externally grounded."""


@dataclass(frozen=True)
class GroundingEvidence:
    math_valid: bool
    physics_consistent: bool
    executable_code: bool
    auditor: str = "adversarial-audit"


def verify_grounding(evidence: GroundingEvidence) -> bool:
    """Adversarial audit gate.

    Hard requirement:
      - executable_code must be True

    Additional reality checks:
      - math_valid and physics_consistent must also be True

    Returns True only when all grounding constraints pass, otherwise raises.
    """
    if not evidence.executable_code:
        raise GroundingVetoError("Reality veto: executable verification failed.")

    if not evidence.math_valid:
        raise GroundingVetoError("Reality veto: mathematical consistency failed.")

    if not evidence.physics_consistent:
        raise GroundingVetoError("Reality veto: physical consistency failed.")

    return True


def save_bloom_if_grounded(
    bloom_payload: Mapping[str, object],
    evidence: GroundingEvidence,
    output_dir: str | Path = "W-DLRA/02_WINGZ/lift_protocols",
) -> Path:
    """Persist a Bloom only when reality checks pass.

    Fails loudly by propagating GroundingVetoError when audit fails.
    """
    verify_grounding(evidence)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_path = output_path / f"bloom_{timestamp}.md"

    lines = [
        "# Grounded Bloom",
        f"- auditor: {evidence.auditor}",
        f"- executable_code: {evidence.executable_code}",
        f"- math_valid: {evidence.math_valid}",
        f"- physics_consistent: {evidence.physics_consistent}",
        "",
        "## Payload",
    ]
    lines.extend(f"- {k}: {v}" for k, v in bloom_payload.items())

    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return file_path
