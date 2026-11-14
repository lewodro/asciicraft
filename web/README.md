# VOXELTERM web build

A static, dependency-free version of the terminal voxel world. Two files:

| File | Purpose |
| --- | --- |
| `index.html` | canvas renderer, input, HUD, seed UI |
| `engine.js` | Perlin noise, world generation, camera, DDA raycaster |

## Run locally

Open `index.html` directly, or serve the folder:

```bash
python3 -m http.server 8000
# http://localhost:8000/web/
```

## Upload

Copy both files to any static host, keeping them in the same directory:

- GitHub Pages: commit this folder, enable Pages on the branch
- Netlify / Vercel / Cloudflare Pages: publish the folder as-is
- S3 / nginx / shared hosting: upload both files

No build step, no server code, no external requests. The page works from
`file://` too.

## Links and options

```
?seed=1337              load a specific world (0 … 4294967295)
?seed=42&mode=half      start in half-block mode
?seed=42&fov=90         field of view in degrees (40 … 120)
?look=0.7               look sensitivity multiplier (0.2 … 3.0)
```

The terminal equivalent of `?look=` is `--look`. The full RGB → glyph → ANSI
pipeline is documented in [`../docs/ascii-rendering.md`](../docs/ascii-rendering.md).

Modes: `ascii-color` (default), `ascii-mono`, `half`. Press **M** to cycle;
the URL updates to match. **R** generates a new random seed.

## Controls

| Input | Action |
| --- | --- |
| `W` `A` `S` `D` | move |
| arrow keys / mouse drag | look |
| `Space` / `C` | fly up / down |
| `E` | run |
| `M` | render mode |
| `R` | new seed |
| `Q` / `Esc` | pause |

The seed box and **Resume** button appear when paused.

## Notes

The engine is a faithful port of the Python implementation. `tools/web_parity.py`
checks that the same seed produces an identical voxel grid and near-identical
frames. The browser renders ASCII glyphs onto a 2D canvas with per-run colour
batching; the world grid is a 21 MB `Uint8Array` generated at load time.
