#!/usr/bin/env python3
"""Generate the integration icon: a glowing orange ring (a nixie "0") on a dark tile.

Usage: python scripts/make_icon.py custom_components/puri_nixie_clock/brand/icon.png
Standard library only. The icon is generic and uses no vendor artwork.
"""

from __future__ import annotations

import math
import struct
import sys
import zlib

SIZE = 256
SAMPLES = 3  # supersampling per axis, for smooth edges


def pixel(x: float, y: float) -> tuple[float, float, float, float]:
    """Return RGBA (0..1) at a point of the 256x256 canvas."""
    # Rounded tile.
    radius, margin = 44.0, 6.0
    cx, cy = abs(x - SIZE / 2), abs(y - SIZE / 2)
    half = SIZE / 2 - margin - radius
    dx, dy = max(cx - half, 0.0), max(cy - half, 0.0)
    if math.hypot(dx, dy) > radius:
        return 0.0, 0.0, 0.0, 0.0
    r, g, b = 0.09, 0.09, 0.11
    # Glowing ring: an ellipse outline, taller than wide, like the digit 0.
    ex, ey = (x - SIZE / 2) / 54.0, (y - SIZE / 2) / 86.0
    d = abs(math.hypot(ex, ey) - 1.0) * 54.0  # distance from the ring centre line, in pixels
    core = max(0.0, 1.0 - d / 9.0)
    glow = math.exp(-((d / 26.0) ** 2)) * 0.55
    r += core * 0.95 + glow * 1.0
    g += core * 0.55 + glow * 0.38
    b += core * 0.15 + glow * 0.05
    return min(r, 1.0), min(g, 1.0), min(b, 1.0), 1.0


def render() -> bytes:
    """Render the canvas as raw RGBA scanlines, each prefixed with filter type 0."""
    rows = bytearray()
    for py in range(SIZE):
        rows.append(0)
        for px in range(SIZE):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    r, g, b, a = pixel(px + (sx + 0.5) / SAMPLES, py + (sy + 0.5) / SAMPLES)
                    acc[0] += r * a
                    acc[1] += g * a
                    acc[2] += b * a
                    acc[3] += a
            alpha = acc[3] / SAMPLES**2
            scale = acc[3] or 1.0
            rows += bytes(
                [
                    round(acc[0] / scale * 255),
                    round(acc[1] / scale * 255),
                    round(acc[2] / scale * 255),
                    round(alpha * 255),
                ]
            )
    return bytes(rows)


def chunk(kind: bytes, data: bytes) -> bytes:
    """Build one PNG chunk."""
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def main() -> None:
    """Write the PNG to the path given on the command line."""
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(render(), 9))
        + chunk(b"IEND", b"")
    )
    with open(sys.argv[1], "wb") as handle:
        handle.write(png)


if __name__ == "__main__":
    main()
