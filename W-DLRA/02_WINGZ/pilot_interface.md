# Pilot Interface Protocol (Mobile Surfer)

## Intent
Deliver compressed, high-truth status packets from the WRM stack to a mobile pilot interface.

## Packet Fields
- `manifold_status`: stable | unstable | vetoed
- `entropy`: normalized 0..1
- `coherence`: normalized 0..1
- `grounding`: passed | failed
- `next_action`: hold | rotate | reject

## Fail-Loud Rule
If `grounding = failed` or entropy exceeds threshold, the interface must display **VETO** and suppress bloom publication.
