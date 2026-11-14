# VOXELTERM

A procedurally generated voxel world, raycast into **coloured ASCII characters** —
in your terminal, or in a single static web page.

- 1024 × 256 × 80 voxels (21 million cells) of hills, lakes, snow-capped ridges,
  caves and trees, all generated from one seed
- about **five minutes** to walk across the world at walking speed
- truecolor ASCII with directional face light, procedural grain, ambient
  occlusion and exponential distance fog
- smooth WASD flight, arrow-key look, sprint, instant reseeding
- **zero dependencies**: Python standard library only; the web build is two
  static files with no libraries and no build step

```
                             .::.
        ...                 .:;;;;:.        ..
      .:;;;:.             .;;;;;;;;;:.    .:;;:.
   ..:;;;;;;;:..        .:;;;;;;;;;;;;;:.:;;;;;:.
  .:;;;;;;;;;;;;;:.   .:;;;;;;;;;;;;;;;;;;;;;;;;:.
 :;;;;;;;;;;;;;;;;;:.;;;;;;;;;;;;;;;;;;;;;;;;;;;;:
```

## Quick start

### Terminal (macOS, Linux, WSL)

```bash
cd voxelterm
./run.sh                 # or: python3 main.py
```

Requires Python **3.9+**. The first full world takes about 7 seconds to
generate; the view then opens in the alternate screen. Press **Q** to quit.

Other launch styles:

```bash
python3 -m voxelterm                     # run as a module
pip install -e .                         # optional install
voxelterm                                # console script after install
```

Native Windows has no `termios`, so the interactive terminal is not available
there. Use **WSL**, or open the web build below.

### Browser

```bash
./serve.sh                               # http://localhost:8000/web/
```

Then open <http://localhost:8000/web/>. You can also open `web/index.html`
directly from disk — there is no server logic and no build step. On Windows use
`serve.bat`.

## Controls

| Key | Action |
| --- | --- |
| `W` `A` `S` `D` | move horizontally |
| `←` `→` | look left / right |
| `↑` `↓` | look up / down |
| `Space` | fly up |
| `C` or `X` | fly down |
| `E` | sprint (1.8×) |
| `M` | cycle `ascii-color → half → ascii-mono` |
| `R` | generate a new random world |
| `[` `]` | lower / raise render quality |
| `Q`, `Esc` (or Ctrl-C / Ctrl-D) | quit |

Terminals cannot report a bare Shift key, so `C`/`X` is the portable descend
key and `E` is hold-to-sprint.

Web controls are the same, with mouse drag or arrow keys to look. `Q`/`Esc`
pauses and shows the seed box.

### Look sensitivity

Look speed has a comfortable default and can be scaled without editing code:

```bash
./run.sh --look 0.7        # slower, 70% of default
./run.sh --look 1.4        # faster
```

In the browser use the matching URL parameter:

```
http://localhost:8000/web/?look=0.7
```

`--look` accepts `0.2`–`3.0`; values outside that range are clamped. The default
is `1.0`.

## One-shot modes

No TTY is needed for these:

```bash
# Write one frame (raw ANSI escape codes) to a file
python3 main.py --snapshot frame.ansi --width 160 --height 48

# Measure render throughput without opening the UI
python3 main.py --benchmark 30 --width 160 --height 48 --mode ascii-color

# Use a small 256x128x80 world for quick control testing
python3 main.py --small

# Render a PNG preview in half-block mode
python3 tools/preview.py --seed 1337 --out preview.png
```

## CLI options

```
--seed N             world seed (default 1337)
--mode MODE          ascii-color (default) | half | ascii-mono
--fov DEG            horizontal field of view (default 76)
--look SCALE         look sensitivity multiplier 0.2..3.0 (default 1.0)
--width / --height   render size in character cells (0 = terminal size)
--pixels N           approximate ray budget for automatic layout
--workers N          0 = auto, 1 = serial forked renderer
--serial             disable fork-based parallel bands
--no-hud             hide the status line
--world-width/-depth/-height N   custom world size
--small              shorthand for 256 x 128 x 80
--snapshot FILE      render one frame and exit
--benchmark N        render N frames and report FPS
```

Default world and scale:

| Property | Value |
| --- | --- |
| Grid | 1024 × 256 × 80 voxels (21 M cells) |
| Sea level | y = 29 |
| Walking speed | 3.4 blocks/s |
| Crossing the 1024-wide world | ≈ 5 minutes (≈ 2.8 min sprinting) |
| Spawn | high, open ground near the middle with water in view |
| Default seed | 1337 |

## How the ASCII rendering works

Every character cell gets one ray. The ray hits a voxel face, the procedural
shader returns an RGB colour, and that colour is reduced to **one printable
glyph plus a foreground colour**.

The glyph is chosen from a 70-character density ramp:

```text
 .'`^",:;Il!i><~+_-?][}{1)(|\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$
```

Brightness selects the glyph; hue stays in the colour channel:

```python
lum  = (0.2126*R + 0.7152*G + 0.0722*B) / 255   # Rec. 709 luminance
tone = lum ** 0.72                              # lift the mid-tones
idx  = int(tone * (len(RAMP) - 1) + 0.5)        # pick a glyph
fg   = (min(255, int(R*1.10 + 8)), ...)         # keep it legible on black
```

Shading happens before that conversion: six face directions get deliberately
different light levels so cubes still read as cubes, hash-based grain supplies
grass blades and stone veins, a three-voxel probe darkens tight corners, water
gets animated wave bands, and distance fades into the same sky gradient that the
sun and horizon use.

The optional `half` mode uses `▀` with independent top and bottom colours for
twice the vertical resolution; `ascii-mono` keeps the glyphs but uses one grey
value per cell.

**Full explanation with the exact constants, worked examples and tuning
knobs: [`docs/ascii-rendering.md`](docs/ascii-rendering.md).**

### Performance

Measured on the development machine (arm64 macOS, 6 forked workers), 160×48
character cells, after world generation:

| Mode | Pixels | FPS |
| --- | --- | --- |
| `ascii-color` | 160 × 48 | ≈ 60 |
| `half` | 160 × 96 | ≈ 31 |

Full Python world generation takes ≈ 7 s; the small world is under 1 s. The
renderer splits scanlines across forked workers; `--serial` disables that, and
auto mode falls back to serial where `fork` is unavailable.

## Web build

`web/index.html` + `web/engine.js` are a self-contained static build.

```bash
./serve.sh
# open http://localhost:8000/web/
```

To publish, upload the two files together to any static host — GitHub Pages,
Netlify, Vercel, Cloudflare Pages, S3, or a folder on your own server. No build
step, no dependencies, no external requests. If you publish the whole
repository, the root `index.html` redirects to `web/`.

The seed lives in the URL, so a view is shareable:

```
https://example.com/web/?seed=1337
https://example.com/web/?seed=42&mode=ascii-mono
https://example.com/web/?seed=42&fov=90&look=0.7
```

The browser engine is a direct port of the terminal engine: the same MT19937
seeding, Perlin noise, terrain/cave/tree generation, DDA traversal and shader.
`tools/web_parity.py` verifies that seed 1337 produces an identical voxel grid
in both implementations and that rendered frames agree to ~99% of pixels
(remaining differences are last-bit `sin`/`cos` variations between libms).

## Project layout

```
voxelterm/
  README.md                 this file
  LICENSE                   MIT
  pyproject.toml            optional packaging + `voxelterm` console script
  main.py                   entry point
  run.sh                    terminal launcher
  serve.sh / serve.bat      static web server launchers
  index.html                redirects a published repo to web/
  docs/
    ascii-rendering.md      the RGB -> glyph -> ANSI pipeline in detail
  voxelterm/
    blocks.py               block ids, face lighting, occluder set
    noise.py                classic Perlin 2D/3D + fBm
    world.py                height field, caves, trees, chunks, 8^3 macro cache
    camera.py               first-person basis, movement, look limits
    raycaster.py            hierarchical voxel DDA + surface shader
    ansi.py                 ASCII ramp -> TrueColor ANSI frame buffer
    terminal.py             raw terminal session + repeat-aware key parser
    parallel.py             fork-based scanline bands
    app.py                  main loop, layout, modes, snapshot/benchmark
  web/
    engine.js               JS port of noise, world, camera and raycaster
    index.html              canvas ASCII renderer, input, HUD, seed UI
    README.md               web-specific notes and deploy options
  tools/
    preview.py              render a frame to PNG (half-block)
    pty_test.py             drive the interactive app through a pseudo-terminal
    web_check.js            headless engine checks (jsc)
    web_frame.js            dump one web frame as PPM (jsc)
    web_dom_test.js         DOM-stubbed browser smoke test (jsc)
    web_parity.py           compare JS output with the Python engine
```

## How it works

**World.** A domain-warped continental fBm plus a ridged mountain mask builds the
height map. Columns are filled with stone/dirt/grass/sand/snow, water fills up to
sea level, two intersecting 3D noise isosurfaces carve tunnel networks plus
larger caverns, and a jittered lattice plants trees. The dense `bytearray` is
mirrored into 16³ chunks for inspection, while an 8³ occupancy array lets the
ray tracer jump over empty air.

**Tracing.** Each character cell gets a ray from an orthonormal camera basis.
A coarse DDA walks 8³ macro cells until it finds an occupied one, then an exact
voxel DDA walks only that segment. Hits return block id, face normal, face UV and
distance. Coefficients are precomputed per resize, so the per-ray cost is one
multiply-add per ray component.

**Compositing.** The shader returns linear-ish RGB; face light, AO and fog are
applied, and the ANSI encoder turns packed RGB into one string with minimal
escape sequences (colour only changes when it must). The game loop performs one
`stdout.write` per frame and never clears the screen between frames.

## Development checks

```bash
python3 -m py_compile main.py voxelterm/*.py tools/*.py
python3 tools/pty_test.py --small --width 70 --height 18   # input/quit/mode test
python3 tools/web_parity.py                                # Python <-> JS parity
```

`tools/web_dom_test.js` and the other `tools/*.js` files run under the macOS
JavaScriptCore shell (`jsc`). They are development helpers, not required to play.
The JS tools assume the repository root as the working directory.

## Notes and limits

- The terminal renderer needs a TrueColor terminal (iTerm2, Terminal.app, most
  modern Linux terminals, Windows Terminal via WSL).
- Interactive mode requires a TTY; use `--snapshot` or `--benchmark` when
  redirecting output.
- Regenerating a full world takes a few seconds in Python; the web engine
  generates the same grid in about 0.2 s.
- There is no persistence or block editing yet — the world is read-only.

## License

MIT. See [`LICENSE`](LICENSE).
