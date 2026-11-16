#!/usr/bin/env python3
"""Time the three stages of a frame: world generation, raycast, ANSI encode.

This is a dependency-free profiling helper. It gives a stable baseline before
renderer or encoder changes, and can optionally show Python's own hot spots.

Usage:
    python3 tools/profile_render.py --small --frames 8
    python3 tools/profile_render.py --frames 20 --cprofile
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voxelterm.ansi import encode_frame  # noqa: E402
from voxelterm.camera import Camera  # noqa: E402
from voxelterm.raycaster import RaycastRenderer  # noqa: E402
from voxelterm.world import World  # noqa: E402


def _args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--width", type=int, default=120)
    ap.add_argument("--height", type=int, default=34)
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--mode", default="ascii-color",
                    choices=("ascii-color", "half", "ascii-mono"))
    ap.add_argument("--small", action="store_true",
                    help="use the 256 x 128 x 80 test world")
    ap.add_argument("--cprofile", action="store_true",
                    help="profile a single raycast + encode pass")
    return ap.parse_args()


def _mean_ms(samples: list[float]) -> float:
    return statistics.fmean(samples) * 1000.0


def main() -> int:
    args = _args()
    dims = (256, 128, 80) if args.small else (1024, 256, 80)

    t0 = time.perf_counter()
    world = World(args.seed, *dims).generate()
    gen_ms = (time.perf_counter() - t0) * 1000.0
    spawn = world.spawn
    cam = Camera(spawn[0], spawn[1], spawn[2], spawn[3], spawn[4])
    renderer = RaycastRenderer(world, cam, args.width, args.height, args.mode)

    # Warm up caches and the allocator before timing.
    pixels = renderer.render(0.0)
    encode_frame(pixels, renderer.width, renderer.pixel_height, args.mode)

    render_ms: list[float] = []
    encode_ms: list[float] = []
    for i in range(max(1, args.frames)):
        t0 = time.perf_counter()
        pixels = renderer.render(i * 0.03)
        render_ms.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        encode_frame(pixels, renderer.width, renderer.pixel_height, args.mode)
        encode_ms.append(time.perf_counter() - t0)

    cells = args.width * renderer.pixel_height
    print(f"world       {dims[0]} x {dims[1]} x {dims[2]} in {gen_ms:.0f} ms")
    print(f"grid        {cells} pixels, {args.mode}")
    print(f"raycast     {_mean_ms(render_ms):7.2f} ms/frame")
    print(f"ansi encode {_mean_ms(encode_ms):7.2f} ms/frame")
    print(f"frame total {_mean_ms(render_ms) + _mean_ms(encode_ms):7.2f} ms "
          f"-> {1000.0 / (_mean_ms(render_ms) + _mean_ms(encode_ms)):.1f} fps")

    if args.cprofile:
        prof = cProfile.Profile()
        prof.enable()
        px = renderer.render(0.5)
        encode_frame(px, renderer.width, renderer.pixel_height, args.mode)
        prof.disable()
        out = io.StringIO()
        pstats.Stats(prof, stream=out).sort_stats("cumulative").print_stats(12)
        print("\n" + out.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
