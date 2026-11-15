# Changelog

All notable changes to ASCIICRAFT are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
