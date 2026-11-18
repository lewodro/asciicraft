# Changelog

All notable changes to ASCIICRAFT are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Four surface biomes — plains, forest, savanna and desert — driven by a
  low-frequency heat/moisture map. Biomes tint the grass and control tree and
  cactus density.
- Cabins and ruins as explorable landmarks. The HUD points to the nearest one,
  counts sites as you reach them, and turns the counter over on a reseed.
- Orbiting birds, drawn as projected blobs with per-frame occlusion, including
  one flock visible from the spawn vista.
- Cacti with ridged stems and arms in the desert biome.
- Cave decoration: stalagmites, stalactites and exposed gold ore veins.
- `tools/profile_render.py` reports per-stage world generation, raycast and
  ANSI-encode timings; `tools/check_repo.py` runs it as part of the checks.
- The browser intro card now holds for at least 2.2 seconds, even though world
  generation finishes in a fraction of that time.

### Changed

- The ANSI encoder caches escape strings, emits a single background sequence
  per row and writes through a byte buffer, cutting encode time by roughly a
  quarter.
- Cave carving samples a 3-voxel lattice instead of testing every voxel,
  shortening the cave stage without changing the tunnel shapes.
- Camera movement uses an exponential velocity response in both builds; arrow
  key look ramps in over about a tenth of a second and glides on release.
- Brighter, more saturated in-game colours: raised face-light levels, an
  exposure/vibrance grade before fog, and a stronger ANSI glyph lift. The new
  palette applies to the terminal and browser builds in every render mode.
- Regenerated the README screenshots with the new palette.

### Fixed

- `tools/screenshot.py` used a stale glyph lift constant, so README captures
  were darker than the real renderer. It now matches `ansi.py` exactly.

## [1.0.0] - 2026-11-14

The first public release: a zero-dependency terminal renderer and a matching
static browser build.

### Added

- Procedural 1024 × 256 × 80 voxel world with hills, water, beaches, caves,
  forests and snow-capped ridges.
- Hierarchical voxel DDA raycaster with an 8³ macro-cell skip pass.
- Truecolor ASCII renderer with a 70-glyph density ramp, Rec. 709 luminance,
  mid-tone lift and per-cell foreground colour.
- Stylised six-face lighting, hash-based material grain, ambient occlusion,
  animated water and exponential sky fog.
- Three render modes: `ascii-color`, `half` (independent top/bottom colours) and
  `ascii-mono`.
- Interactive terminal app with WASD movement, arrow-key look, sprint, flight,
  live mode cycling, quality controls and instant reseeding.
- Snapshot and benchmark modes for non-interactive use.
- Fork-based scanline renderer with automatic serial fallback.
- Dependency-free browser port sharing the same MT19937, Perlin, terrain,
  camera, traversal and shader code.
- Seed, mode, FOV and look sensitivity stored in the browser URL.
- MIT licensing, launch scripts, optional packaging and GitHub Actions CI.
- Reproducible screenshot renderer and README gallery.
- Full ASCII pipeline documentation with constants and worked examples.

### Changed

- Look sensitivity defaults to a calmer speed and can be scaled with `--look`
  in the terminal or `?look=` in the browser.
- User-facing branding is ASCIICRAFT; the engine package remains `voxelterm`.
- Added `asciicraft` as a console entry point alongside `voxelterm`.

### Fixed

- Held keys now reach the movement loop instead of only firing on the first
  keypress, and a lone Escape is flushed correctly.
- `Q` and Escape quit cleanly, and the raw terminal is always restored.
- The web build guards `history.replaceState` when opened from `file://`.

### Performance

- 160 × 48 `ascii-color`: about 60 FPS on an arm64 macOS laptop with six workers.
- 160 × 96 `half`: about 31 FPS under the same conditions.
- Full Python world generation: about 7 seconds; browser generation about 0.2 s.
