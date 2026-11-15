# Screenshot assets

These are real 123 × 34 ASCII-color frames produced by the engine, rasterised
with a terminal-style monospace font. They are not mockups or concept art.

| File | Seed | Camera | Mode |
| --- | ---: | --- | --- |
| `asciicraft-highlands.png` | 1337 | `x513 y55 z114`, yaw 1.374, pitch −0.40 | `ascii-color` |
| `asciicraft-valley.png` | 1337 | `x520 y53 z106`, yaw 2.300, pitch −0.30 | `ascii-color` |
| `asciicraft-snowline.png` | 600970973 | `x490 y63 z111`, yaw 1.374, pitch −0.55 | `ascii-color` |

The world is 1024 × 256 × 80 voxels in each image. The HUD line is part of the
renderer output; the FPS value is illustrative.

## Regenerate

`tools/screenshot.py` renders a frame with the real raycaster and uses headless
Chrome to draw the glyph/colour cells to a PNG. Chrome is the only external
requirement, and only for this development tool.

```bash
python3 tools/screenshot.py --seed 1337 --x 513 --y 55 --z 114 \
  --yaw 1.374 --pitch -0.40 --fps 238.3 \
  --out assets/asciicraft-highlands.png

python3 tools/screenshot.py --seed 1337 --x 520 --y 53 --z 106 \
  --yaw 2.30 --pitch -0.30 --fps 236.6 \
  --out assets/asciicraft-valley.png

python3 tools/screenshot.py --seed 600970973 --x 490 --y 63 --z 111 \
  --yaw 1.374 --pitch -0.55 --fps 215.7 \
  --out assets/asciicraft-snowline.png
```

On Linux, set `CHROME=/usr/bin/google-chrome` (or the equivalent) if Chrome is
not in a standard location.
