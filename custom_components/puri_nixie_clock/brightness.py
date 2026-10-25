"""Pure brightness logic (SPEC.md section 4.4)."""

from __future__ import annotations

from .const import BRIGHTNESS_STEPS


def auto_target(
    elevation: float,
    lo_elev: float = -6.0,
    hi_elev: float = 10.0,
    lo_val: int = 6,
    hi_val: int = 256,
) -> int:
    """Return the brightness step for a solar elevation in degrees.

    The brightness rises linearly from `lo_val` at `lo_elev` to `hi_val` at `hi_elev`
    and is rounded to the nearest step; on a tie the lower step wins.
    """
    fraction = min(1.0, max(0.0, (elevation - lo_elev) / (hi_elev - lo_elev)))
    raw = lo_val + fraction * (hi_val - lo_val)
    return min(
        (step for step in BRIGHTNESS_STEPS if lo_val <= step <= hi_val),
        key=lambda step: (abs(step - raw), step),
    )
