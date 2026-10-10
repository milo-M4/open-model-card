"""Card schema constants. The single source of truth for the card format.

A card's `schema_version` field matches SCHEMA_VERSION. Old cards with a
lower version still load (the loader is forgiving about new fields), but
fields removed from a major version will not be present in older cards.

Comparability tags travel with the metric they describe:

    machine-local    — speed, memory. Only meaningful on the same machine.
    model-portable   — task pass/fail. Comparable across machines.
    engine-portable  — behavior with respect to engine quirks.
"""

from __future__ import annotations

SCHEMA_VERSION = "1.0"

# Comparability tags. Use these constants everywhere a card field carries a
# comparability value, so the set is closed and typos are caught at import.
MACHINE_LOCAL = "machine-local"
MODEL_PORTABLE = "model-portable"
ENGINE_PORTABLE = "engine-portable"

VALID_COMPARABILITY = {MACHINE_LOCAL, MODEL_PORTABLE, ENGINE_PORTABLE}

# Field names whose values are machine-local. Used by the compare view to
# decide whether to hide a metric in cross-machine mode.
MACHINE_LOCAL_FIELDS = {"speed", "memory"}

# The 12-test battery is fixed across all versions. Adding tests requires
# bumping the schema minor version.
NUMBER_OF_TESTS = 12

# Verdict thresholds for the plain-summary verdict language. Calibrated per
# model-size band. Tunable by the operator in their operator.md.
SPEED_BANDS = (
    # (band_name, max_param_b, fast_min_tps, average_min_tps)
    ("small", 8, 60, 20),
    ("medium", 15, 30, 10),
    ("large", 35, 15, 5),
    ("huge", 10**9, 8, 3),
)


def speed_band(param_b: float) -> tuple[str, float, float]:
    """Return (band_name, fast_min_tps, average_min_tps) for the model size."""
    for name, max_b, fast, average in SPEED_BANDS:
        if param_b < max_b:
            return name, fast, average
    return SPEED_BANDS[-1][0], SPEED_BANDS[-1][2], SPEED_BANDS[-1][3]


def speed_verdict(tok_per_s: float | None, param_b: float | None) -> str:
    """Turn a speed number into a plain-language verdict.

    Returns "fast", "average", "slow", or "unknown" if data is missing.
    Falls back to absolute thresholds when param_b is not known.
    """
    if tok_per_s is None:
        return "unknown"
    if param_b is None:
        # No size band — use absolute thresholds from the large band.
        _, _, average, slow = 15, 5, 5, 5
        if tok_per_s >= 15:
            return "fast"
        if tok_per_s >= 5:
            return "average"
        return "slow"
    _, fast, average = speed_band(param_b)
    if tok_per_s >= fast:
        return "fast"
    if tok_per_s >= average:
        return "average"
    return "slow"
