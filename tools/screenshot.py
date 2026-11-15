#!/usr/bin/env python3
"""Render a terminal-style PNG from the real ASCII frame buffer.

This is a development helper: it uses headless Chrome to rasterise an HTML
representation of the exact glyph/colour cells produced by the engine.  It is
not required to play ASCIICRAFT, and it has no Python dependencies.

Examples:
    python3 tools/screenshot.py --seed 1337 --out assets/terrain.png
    python3 tools/screenshot.py --seed 1337 --x 520 --y 53 --z 106 \
        --yaw 2.2 --pitch -0.08 --out assets/hills.png

Chrome is looked up in the usual macOS locations; set CHROME=/path/to/chrome
to override it.
"""

from __future__ import annotations

import argparse
import html
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voxelterm.ansi import ASCII_RAMP, _luminance  # noqa: E402
from voxelterm.camera import Camera  # noqa: E402
from voxelterm.raycaster import MODE_ASCII_COLOR, RaycastRenderer  # noqa: E402
from voxelterm.world import World  # noqa: E402

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)

RAM_LAST = len(ASCII_RAMP) - 1
HUD_BG = (18, 24, 32)
HUD_FG = (155, 185, 210)


def find_chrome() -> str:
    env = os.environ.get("CHROME")
    if env:
        return env
    for candidate in CHROME_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return found
    raise SystemExit("screenshot.py: headless Chrome not found; set CHROME=...")


def rgb(cell: int) -> tuple[int, int, int]:
    return ((cell >> 16) & 255, (cell >> 8) & 255, cell & 255)


def lifted(cell: int) -> tuple[int, int, int]:
    r, g, b = rgb(cell)
    return (min(255, int(r * 1.10 + 8)),
            min(255, int(g * 1.10 + 8)),
            min(255, int(b * 1.10 + 8)))


def cell_char(cell: int) -> str:
    lum = _luminance(cell) ** 0.72
    return ASCII_RAMP[int(lum * RAM_LAST + 0.5)]


def build_html(pixels: list[int], width: int, height: int,
               status: str) -> str:
    rows: list[str] = []
    for y in range(height):
        base = y * width
        row: list[str] = []
        run = ""
        run_color = None
        for x in range(width):
            cell = pixels[base + x]
            ch = cell_char(cell)
            color = lifted(cell)
            if color != run_color:
                if run:
                    row.append(f'<span style="color:rgb{run_color}">{html.escape(run)}</span>')
                run = ch
                run_color = color
            else:
                run += ch
        if run:
            row.append(f'<span style="color:rgb{run_color}">{html.escape(run)}</span>')
        rows.append("".join(row))

    hud = status.replace("\t", " ")[:width].ljust(width)
    rows.append(f'<span class="hud" style="color:rgb{HUD_FG};'
                f'background:rgb{HUD_BG}">{html.escape(hud)}</span>')
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin:0; padding:0; overflow:hidden; background:#06090e; }}
  body {{ width:{width * 13.089}px; }}
  pre {{
    margin:0; padding:0; background:#06090e;
    font-family:"SF Mono", "Menlo", "DejaVu Sans Mono", monospace;
    font-size:21.8px; line-height:27.5px; font-weight:400;
    letter-spacing:0; white-space:pre; font-kerning:none;
    -webkit-font-smoothing:antialiased;
  }}
  .hud {{ display:block; height:27.5px; line-height:27.5px; }}
</style></head><body><pre>{chr(10).join(rows)}</pre></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--width", type=int, default=123,
                    help="character columns (default: 123)")
    ap.add_argument("--height", type=int, default=34,
                    help="rendered character rows, excluding the HUD (default: 34)")
    ap.add_argument("--x", type=float, default=None)
    ap.add_argument("--y", type=float, default=None)
    ap.add_argument("--z", type=float, default=None)
    ap.add_argument("--yaw", type=float, default=None)
    ap.add_argument("--pitch", type=float, default=None)
    ap.add_argument("--fov", type=float, default=76.0)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--out", default="screenshot.png")
    ap.add_argument("--html-out", default="")
    ap.add_argument("--small", action="store_true")
    args = ap.parse_args()

    dims = (256, 128, 80) if args.small else (1024, 256, 80)
    world = World(args.seed, *dims).generate()
    sx, sy, sz, syaw, spitch = world.spawn
    x = sx if args.x is None else args.x
    y = sy if args.y is None else args.y
    z = sz if args.z is None else args.z
    yaw = syaw if args.yaw is None else args.yaw
    pitch = spitch if args.pitch is None else args.pitch

    view_rows = max(1, args.height)
    cam = Camera(x, y, z, yaw, pitch, args.fov)
    renderer = RaycastRenderer(world, cam, args.width, view_rows,
                               MODE_ASCII_COLOR)
    pixels = renderer.render(0.0)
    status = (f" AC {args.fps:4.1f}fps | seed {args.seed} | ASCII COLOR | "
              f"x{x:.0f}/{world.width} y{y:.0f} z{z:.0f} | "
              f"{args.width}x{view_rows}")
    page = build_html(pixels, args.width, view_rows, status)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.html_out:
        Path(args.html_out).write_text(page, encoding="utf-8")

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(page)
        html_path = fh.name
    try:
        chrome = find_chrome()
        pixel_width = int(round(args.width * 13.089))
        pixel_height = int(round((args.height + 1) * 27.5))
        cmd = [
            chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", "--no-first-run",
            f"--window-size={pixel_width},{pixel_height}",
            f"--screenshot={out.resolve()}",
            f"file://{html_path}",
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    finally:
        os.unlink(html_path)

    print(f"wrote {out} ({args.width}x{args.height} cells, seed {args.seed}, "
          f"x={x:.1f} y={y:.1f} z={z:.1f} yaw={yaw:.3f} pitch={pitch:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
