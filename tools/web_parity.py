#!/usr/bin/env python3
"""Check that the JavaScript web engine matches the Python engine.

Runs the JavaScriptCore shell (`jsc`) headlessly on macOS, then compares:
  * Python MT19937 values, shuffle and randrange output
  * the generated 1024x256x80 voxel grid and height map (FNV checksums)
  * the spawn point
  * a 120x30 raycast frame (pixel and ASCII-character agreement)

Usage: python3 tools/web_parity.py
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voxelterm.ansi import ASCII_RAMP, _luminance  # noqa: E402
from voxelterm.camera import Camera  # noqa: E402
from voxelterm.raycaster import MODE_ASCII_COLOR, RaycastRenderer  # noqa: E402
from voxelterm.world import World  # noqa: E402

JSC_CANDIDATES = (
    "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc",
    shutil.which("jsc"),
)


def find_jsc() -> str | None:
    for cand in JSC_CANDIDATES:
        if cand and Path(cand).exists():
            return cand
    return None


def fnv_bytes(data: bytes, h: int = 2166136261) -> int:
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


def fnv_ints(values, h: int = 2166136261) -> int:
    for v in values:
        h = ((h ^ int(v)) * 16777619) & 0xFFFFFFFF
    return h


def chars(pixels) -> str:
    last = len(ASCII_RAMP) - 1
    return "".join(
        ASCII_RAMP[int(_luminance(c) ** 0.72 * last + 0.5)] for c in pixels
    )


def main() -> int:
    jsc = find_jsc()
    if jsc is None:
        print("web_parity: JavaScriptCore `jsc` not found; skipping")
        return 0

    proc = subprocess.run([jsc, "tools/web_check.js"], cwd=ROOT,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return 1
    js = json.loads(proc.stdout.strip().splitlines()[-1])

    failures: list[str] = []
    rng_failures: list[str] = []
    rng = random.Random(1337)
    randoms = [rng.random() for _ in range(6)]
    arr = list(range(16))
    rng.shuffle(arr)
    rands = [rng.randrange(-3, 7) for _ in range(8)]
    if js["randoms"] != randoms:
        rng_failures.append("MT19937 random() differs")
    if js["shuffled"] != arr:
        rng_failures.append("shuffle differs")
    if js["randranges"] != rands:
        rng_failures.append("randrange differs")
    failures.extend(rng_failures)

    world = World(1337).generate()
    world_failures: list[str] = []
    if js["heightHash"] != fnv_ints(world.height_map):
        world_failures.append("height map checksum differs")
    if js["gridHash"] != fnv_bytes(world.grid):
        world_failures.append("voxel grid checksum differs")
    if js["gridLen"] != len(world.grid):
        world_failures.append("grid length differs")
    if js["biomeHash"] != fnv_bytes(world.biomes):
        world_failures.append("biome map checksum differs")
    if js["biomeLen"] != len(world.biomes):
        world_failures.append("biome map length differs")
    failures.extend(world_failures)
    spawn = tuple(round(v, 6) for v in js["spawn"])
    py_spawn = tuple(round(v, 6) for v in world.spawn)
    if spawn != py_spawn:
        failures.append(f"spawn differs: {spawn} != {py_spawn}")

    frame = subprocess.run([jsc, "tools/web_frame.js"], cwd=ROOT,
                           capture_output=True, text=True)
    tokens = frame.stdout.split()
    w, h = int(tokens[1]), int(tokens[2])
    nums = list(map(int, tokens[4:]))
    js_px = [(nums[i] << 16) | (nums[i + 1] << 8) | nums[i + 2]
             for i in range(0, len(nums), 3)]

    x, y, z, yaw, pitch = world.spawn
    renderer = RaycastRenderer(world, Camera(x, y, z, yaw, pitch),
                               w, h, MODE_ASCII_COLOR)
    py_px = renderer.render(0.0)
    exact = sum(1 for a, b in zip(js_px, py_px) if a == b) / len(py_px)
    diff = [abs(((a >> s) & 255) - ((b >> s) & 255))
            for a, b in zip(js_px, py_px) for s in (16, 8, 0)]
    char_diff = sum(1 for a, b in zip(chars(js_px), chars(py_px)) if a != b)
    char_rate = char_diff / len(py_px)

    print(f"RNG parity: {'ok' if not rng_failures else 'FAIL'}")
    print(f"world checksums: {'ok' if not world_failures else 'FAIL'} "
          f"({js['gridLen']} voxels)")
    print(f"spawn: {py_spawn}")
    print(f"frame {w}x{h}: {exact:.1%} pixels identical, "
          f"{char_rate:.2%} characters differ, mean channel diff "
          f"{sum(diff) / len(diff):.3f}")
    if exact < 0.97:
        failures.append(f"pixel agreement too low: {exact:.2%}")
    if char_rate > 0.02:
        failures.append(f"character mismatch too high: {char_rate:.2%}")

    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("web/engine.js matches the Python engine")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
