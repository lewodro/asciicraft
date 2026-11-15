# How ASCIICRAFT turns a world into ASCII

ASCIICRAFT never draws a polygon. It fires one ray per character cell, asks what
surface that ray hit, converts the surface colour into a **single printable glyph
plus a foreground colour**, and streams those glyphs to the terminal. A frame is
just text — about 8,000 characters for a 160×48 view.

This document explains each conversion in order, with the exact constants used by
`voxelterm/raycaster.py` and `voxelterm/ansi.py`.

---

## 1. The pipeline

```
 world grid (bytes)
        │
        ▼
 [1] one ray per cell  ──►  hit: block, face normal, surface UV, distance
        │
        ▼
 [2] procedural shader ──►  linear-ish RGB  (grass, stone, water, sky)
        │
        ▼
 [3] face light + AO + fog ──►  shaded RGB
        │
        ▼
 [4] luminance ──► gamma curve ──► ramp index ──► glyph
        │
        ▼
 [5] glyph colour  ──►  run-length ANSI tokens
        │
        ▼
 [6] one stdout.write per frame
```

---

## 2. One ray per character cell

For a view of `W` columns and `H` rows the renderer builds `W × H` rays from an
orthonormal camera basis (`forward`, `right`, `up`):

```text
sx = (2 * (px + 0.5) / W - 1) * tan(fov / 2)
sy = (1 - 2 * (py + 0.5) / H) * tan(fov / 2) * aspect

dir = forward + right * sx + up * sy
```

Because the basis is orthonormal, the direction is normalised by folding
`1 / sqrt(1 + sx² + sy²)` into precomputed per-pixel coefficients. There is no
square root in the hot loop.

In ASCII modes one ray equals one character cell, and characters are twice as
tall as they are wide, so `aspect = 2` keeps the world from looking stretched.
In half-block mode two vertical pixels share one cell and `aspect = 1`.

Traversal is hierarchical:

1. an 8×8×8 **macro** grid marks which regions contain any solid voxel;
2. a coarse DDA skips empty macro cells;
3. an exact voxel DDA runs only inside occupied macro cells.

A miss samples the sky gradient; a hit returns the block id, the face normal,
the position inside the face (UV) and the distance.

---

## 3. The shader: RGB before any ASCII happens

Each block has a small procedural material. The shader returns RGB in roughly
display space, before lighting:

| Block | Top / side treatment |
| --- | --- |
| grass | green top with grain; dirt sides; a green lip on upper side pixels |
| dirt | brown with coarse grain and dark pebbles |
| stone | grey with hash grain and a sine vein pattern |
| sand | warm pale grain |
| snow | near-white with darker sparkle flecks |
| wood | ring pattern on end grain, vertical grain on sides |
| leaves | clumpy dark/light green from hash noise |
| water | two crossed sine waves on top, slower bands on the side |

`grain` is a deterministic 32-bit integer hash of block position, face id and
sub-face UV, so the texture never swims when you move and needs no texture
memory.

Then three lighting terms are applied:

```text
light = FACE_LIGHT[normal] * ambient_occlusion
rgb   = material_rgb * light

lum   = 0.2126*R + 0.7152*G + 0.0722*B
rgb   = (lum + (rgb - lum) * 1.12) * 1.18

rgb   = mix(rgb, sky(direction), fog)
fog   = 1 - exp(-(distance / 94)²)
```

`FACE_LIGHT` is deliberately exaggerated:

| Face | Light |
| --- | --- |
| top | 1.00 |
| bottom | 0.44 |
| +X | 0.70 |
| −X | 0.65 |
| +Z | 0.88 |
| −Z | 0.81 |

That difference is what makes a cube read as a cube even after its colour has
been reduced to one character. Ambient occlusion darkens the inside edges of a
face by probing up to three neighbouring voxels; water skips AO so it stays
smooth.

---

## 4. RGB → one glyph

This is the part that makes the image ASCII rather than a mosaic.

### 4.1 Luminance

The shaded RGB is reduced to a perceptual luminance in `[0, 1]`:

```python
lum = (0.2126 * R + 0.7152 * G + 0.0722 * B) / 255
```

These are the Rec. 709 weights: green contributes most, blue least. A dark red
and a dark blue can therefore choose different glyphs even at similar apparent
brightness.

### 4.2 Gamma-ish tone curve

Raw luminance is not evenly distributed: most natural surfaces sit between 0.2
and 0.6, where a linear ramp would waste most of its glyphs. ASCIICRAFT raises
luminance to `0.72`:

```python
tone = lum ** 0.72
```

This lifts the mid-tones and gives grass, stone and water more distinct glyphs.
Pure black stays black and pure white stays white.

### 4.3 Ramp quantisation

The ramp is 70 glyphs, ordered from visually lightest (space) to visually
heaviest (`$`):

```text
 .'`^",:;Il!i><~+_-?][}{1)(|\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$
```

The index is a rounded linear quantisation of the tone:

```python
index = int(tone * (len(ramp) - 1) + 0.5)
glyph = ramp[index]
```

Here is the full ramp with indices, useful when tuning the curve:

```text
 0:' '  1:'.'  2:"'"  3:'`'  4:'^'  5:'"'  6:','  7:':'  8:';'  9:'I'
10:'l' 11:'!' 12:'i' 13:'>' 14:'<' 15:'~' 16:'+' 17:'_' 18:'-' 19:'?'
20:']' 21:'[' 22:'}' 23:'{' 24:'1' 25:')' 26:'(' 27:'|' 28:'\' 29:'/'
30:'t' 31:'f' 32:'j' 33:'r' 34:'x' 35:'n' 36:'u' 37:'v' 38:'c' 39:'z'
40:'X' 41:'Y' 42:'U' 43:'J' 44:'C' 45:'L' 46:'Q' 47:'0' 48:'O' 49:'Z'
50:'m' 51:'w' 52:'q' 53:'p' 54:'d' 55:'b' 56:'k' 57:'h' 58:'a' 59:'o'
60:'*' 61:'#' 62:'M' 63:'W' 64:'&' 65:'8' 66:'%' 67:'B' 68:'@' 69:'$'
```

Examples using colours the shader actually produces:

| Surface | RGB | luminance | tone | index | glyph |
| --- | --- | ---: | ---: | ---: | :---: |
| grass top | 86, 158, 55 | 0.530 | 0.633 | 44 | `C` |
| lit stone side | 101, 107, 113 | 0.416 | 0.532 | 37 | `v` |
| water surface | 34, 117, 187 | 0.409 | 0.526 | 36 | `u` |
| snow | 255, 255, 255 | 1.000 | 1.000 | 69 | `$` |
| sky near horizon | 157, 191, 220 | 0.729 | 0.796 | 55 | `b` |
| dirt in shadow | 47, 33, 20 | 0.137 | 0.240 | 17 | `_` |

The glyph supplies **shape and brightness**; colour is applied separately, so a
`z` can be grass green or mossy stone and still read as a mid-tone.

### 4.4 Glyph colour

Coloured modes paint each glyph with the surface colour, lifted slightly so it
stays legible on the dark background:

```python
R = min(255, int(R * 1.14 + 10))
G = min(255, int(G * 1.14 + 10))
B = min(255, int(B * 1.14 + 10))
```

Monochrome mode instead derives one grey from the same tone:

```python
v = min(255, int(58 + 190 * tone ** 0.9))
```

---

## 5. RGB → ANSI tokens

The encoder in `voxelterm/ansi.py` turns the pixel buffer into one string. Naively
that would be one escape sequence per cell; instead it emits a token only when a
value changes:

```text
ESC[48;2;6;9;14m          set the shared dark background once per row
ESC[38;2;77;132;54m       set foreground for a run of grass
zzzzzzzzzz
ESC[38;2;86;91;95m       switch when the run ends
rrrrr
...
ESC[0m                    reset at the end of the frame
```

A typical frame uses a few hundred colour changes rather than `W × H`. The whole
frame is one Python string and one `stdout.write`, so the terminal never sees a
partially painted image and never needs a clear between frames.

### Half-block mode

`half` mode uses `▀` (U+2580): foreground is the top pixel, background is the
bottom pixel. One character cell carries two independent colours, doubling
vertical resolution:

```text
ESC[38;2;topRGBm ESC[48;2;bottomRGBm ▀
```

It is not ASCII, but it is the highest-fidelity terminal mode and a useful
comparison when tuning the ASCII curve. `M` cycles
`ascii-color → half → ascii-mono`.

### ASCII monochrome mode

Same raycast, same glyph choice, same ramp; only the glyph colour is replaced by
one grey value. This is the mode for terminals where 24-bit colour is
unavailable or where the pure character artwork is the point.

---

## 6. A compact reference implementation

The whole idea in twelve lines:

```python
RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"

def shade_to_cell(r, g, b):
    lum  = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    tone = lum ** 0.72
    idx  = int(tone * (len(RAMP) - 1) + 0.5)
    glyph = RAMP[idx]
    fg = (min(255, int(r * 1.14 + 10)),
          min(255, int(g * 1.14 + 10)),
          min(255, int(b * 1.14 + 10)))
    return glyph, fg
```

Everything else — world generation, DDA traversal, face lighting, AO, fog, wave
animation, ANSI batching — exists to feed plausible RGB into those four lines.

---

## 7. Why it holds together

- **Two independent channels.** Brightness selects the glyph; hue and saturation
  are carried by colour. Reducing either one still leaves a readable image.
- **A large ramp.** 70 glyphs avoid the banding of the usual 10-character ramps
  while still mapping to terminal-safe printable ASCII.
- **Exaggerated face light.** Cube edges survive quantisation because adjacent
  faces differ by up to 56% brightness before the ramp.
- **Tone lift.** The `** 0.72` curve spends more glyphs on the mid-tones that
  dominate grass, stone, leaves and water.
- **Deterministic grain.** Texture is a hash of position, not a texture lookup,
  so the image is stable frame to frame and costs no memory.
- **Sky-coloured fog.** Distant geometry and empty sky converge on the same
  gradient, which hides the ray limit without a hard horizon line.

## 8. Tuning knobs

| Knob | Where | Effect |
| --- | --- | --- |
| ramp string | `voxelterm/ansi.py` | glyph density and artistic feel |
| tone exponent | `ansi.py` (`lum ** 0.72`) | mid-tone contrast |
| colour lift | `ansi.py` (`* 1.14 + 10`) | glyph legibility on dark backgrounds |
| `FACE_LIGHT` | `voxelterm/blocks.py` | cube readability |
| `FOG_DISTANCE` | `voxelterm/raycaster.py` | depth falloff |
| `_SKY_*` | `voxelterm/raycaster.py` | horizon palette and fog colour |

The web build mirrors these values in `web/engine.js`, so a change made in one
place should be made in the other; `tools/web_parity.py` reports drift.
