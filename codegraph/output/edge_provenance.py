"""Map numeric edge confidence to graphify-style provenance labels for exports."""

from __future__ import annotations

# Aligns with README: 1.0 direct, 0.8 barrel, 0.5 star/fallback, 0.2 dynamic
_EXTRACTED_MIN = 0.85
_INFERRED_MIN = 0.35


def edge_provenance(confidence: float) -> str:
    """Return EXTRACTED, INFERRED, or AMBIGUOUS from a 0.0–1.0 confidence score."""
    c = float(confidence)
    if c >= _EXTRACTED_MIN:
        return "EXTRACTED"
    if c >= _INFERRED_MIN:
        return "INFERRED"
    return "AMBIGUOUS"
