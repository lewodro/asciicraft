#!/usr/bin/env python3
"""Render one frame to a PNG for development / README previews.

This is not part of the terminal app.  It uses only the standard library.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voxelterm.camera import Camera  # noqa: E402
from voxelterm.raycaster import MODE_HALF, RaycastRenderer  # noqa: E402
from voxelterm.world import World  # noqa: E402


def write_png(path: str, pixels: list[int], width: int, height: int) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        base = y * width
        for x in range(width):
            c = pixels[base + x]
            raw.extend(((c >> 16) & 255, (c >> 8) & 255, c & 255))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
           chunk(b"IEND", b""))
    Path(path).write_bytes(png)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--width", type=int, default=180)
    ap.add_argument("--height", type=int, default=54)
    ap.add_argument("--out", default="preview.png")
    args = ap.parse_args()

    world = World(args.seed).generate()
    x, y, z, yaw, pitch = world.spawn
    cam = Camera(x, y, z, yaw, pitch)
    r = RaycastRenderer(world, cam, args.width, args.height, MODE_HALF)
    pixels = r.render(0.0)
    write_png(args.out, pixels, r.width, r.pixel_height)
    print(f"seed={args.seed} spawn=({x:.1f},{y:.1f},{z:.1f}) yaw={yaw:.2f} "
          f"pitch={pitch:.2f} -> {args.out} ({r.width}x{r.pixel_height})")


if __name__ == "__main__":
    main()
