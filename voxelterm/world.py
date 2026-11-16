"""Procedural voxel world with chunked storage and a cache-friendly ray grid."""

from __future__ import annotations

import math
import random

from . import blocks
from .noise import PerlinNoise

CHUNK = 16
MACRO = 8
WORLD_WIDTH = 1024
WORLD_DEPTH = 256
WORLD_HEIGHT = 80
SEA_LEVEL = 29

# Surface biomes.  The climate fields are low-frequency, so they are sampled
# on a coarse lattice and stamped into the per-column map; the block edges are
# well below one terminal cell at play resolution.
BIOME_PLAINS = 0
BIOME_FOREST = 1
BIOME_SAVANNA = 2
BIOME_DESERT = 3
BIOME_NAMES = ("plains", "forest", "savanna", "desert")
BIOME_STRIDE = 4


class World:
    """A finite, deterministic Perlin-noise voxel island.

    The authoritative world is split into 16x16x16 chunks.  A dense byte grid
    is kept alongside the chunks because the inner DDA loop accesses millions
    of voxels per second; the flat mirror removes dictionary lookups from the
    hot path while the chunks remain useful for inspection and future edits.
    """

    __slots__ = (
        "seed", "width", "depth", "height", "sea_level",
        "grid", "height_map", "chunks", "spawn", "generation_time",
        "macro", "macro_dims", "macro_size", "macro_top", "timings",
        "biomes",
    )

    def __init__(self, seed: int,
                 width: int = WORLD_WIDTH,
                 depth: int = WORLD_DEPTH,
                 height: int = WORLD_HEIGHT):
        self.seed = int(seed) & 0xFFFFFFFF
        self.width = width
        self.depth = depth
        self.height = height
        self.sea_level = SEA_LEVEL
        self.grid = bytearray(width * depth * height)
        self.height_map = [0] * (width * depth)
        self.chunks: dict[tuple[int, int, int], bytearray] = {}
        self.spawn = (width * 0.5, height * 0.72, depth * 0.5, 0.0, 0.0)
        self.generation_time = 0.0
        self.macro = bytearray()
        self.macro_dims = (1, 1, 1)
        self.macro_size = MACRO
        self.macro_top = bytearray()
        self.timings: dict[str, float] = {}
        self.biomes = bytearray(width * depth)

    # ------------------------------------------------------------------ access
    def index(self, x: int, y: int, z: int) -> int:
        return x + self.width * (z + self.depth * y)

    def biome_at(self, x: int, z: int) -> int:
        if 0 <= x < self.width and 0 <= z < self.depth:
            return self.biomes[x + self.width * z]
        return BIOME_PLAINS

    def biome_name(self, x: int, z: int) -> str:
        return BIOME_NAMES[self.biome_at(int(x), int(z))]

    def in_bounds(self, x: int, y: int, z: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and 0 <= z < self.depth

    def get_block(self, x: int, y: int, z: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height and 0 <= z < self.depth:
            return self.grid[x + self.width * (z + self.depth * y)]
        return blocks.AIR

    def is_occluder(self, x: int, y: int, z: int) -> bool:
        if 0 <= x < self.width and 0 <= y < self.height and 0 <= z < self.depth:
            return self.grid[x + self.width * (z + self.depth * y)] in blocks.OCCLUDERS
        return False

    def set_block(self, x: int, y: int, z: int, block: int) -> None:
        if self.in_bounds(x, y, z):
            self.grid[self.index(x, y, z)] = block

    def surface_height(self, x: int, z: int) -> int:
        if 0 <= x < self.width and 0 <= z < self.depth:
            return self.height_map[x + self.width * z]
        return 0

    # -------------------------------------------------------------- generation
    def generate(self) -> "World":
        import time
        started = time.perf_counter()
        mark = started
        self.timings = {}
        noise = PerlinNoise(self.seed)
        rng = random.Random(self.seed ^ 0x9E3779B9)
        self.grid = bytearray(self.width * self.depth * self.height)
        self.height_map = [0] * (self.width * self.depth)

        sea = self.sea_level
        width = self.width
        depth = self.depth
        height = self.height
        grid = self.grid
        heights = self.height_map

        # 0. Climate map.  Heat and moisture are independent low-frequency
        #    fields; their combination picks the surface material and the tree
        #    density later on.  Sampling every BIOME_STRIDE columns keeps this
        #    stage under a few milliseconds.
        biomes = self.biomes
        stride = BIOME_STRIDE
        for bz in range(0, depth, stride):
            for bx in range(0, width, stride):
                heat = noise.noise2(bx * 0.0046 + 61.0, bz * 0.0046 - 37.0)
                wet = noise.noise2(bx * 0.0063 - 23.0, bz * 0.0063 + 49.0)
                if heat > 0.20 and wet < 0.10:
                    biome = BIOME_DESERT
                elif wet > 0.20:
                    biome = BIOME_FOREST
                elif heat > 0.10:
                    biome = BIOME_SAVANNA
                else:
                    biome = BIOME_PLAINS
                z_end = min(bz + stride, depth)
                x_end = min(bx + stride, width)
                for zz in range(bz, z_end):
                    row = width * zz
                    for xx in range(bx, x_end):
                        biomes[row + xx] = biome

        self.timings["biome"] = time.perf_counter() - mark
        mark = time.perf_counter()

        # 1. Height field: domain-warped continents, rolling hills and a broad
        #    ridged mountain mask.  This is intentionally more interesting than
        #    a single fBm octave stack.
        for z in range(depth):
            for x in range(width):
                wx = x + noise.noise2(x * 0.019 + 7.1, z * 0.019 - 2.3) * 9.0
                wz = z + noise.noise2(x * 0.019 - 4.7, z * 0.019 + 8.9) * 9.0
                continental = noise.fbm2(wx * 0.0074 + 11.2, wz * 0.0074 - 3.7, 5)
                hills = noise.fbm2(x * 0.029 - 8.0, z * 0.029 + 4.0, 4)
                ridge_field = noise.fbm2(x * 0.0112 + 21.3, z * 0.0112 - 9.1, 3)
                ridge = max(0.0, (1.0 - abs(ridge_field)) - 0.65) / 0.35
                mountain = (ridge ** 1.8) * 28.0
                detail = noise.noise2(x * 0.13 + 3.0, z * 0.13 - 6.0)
                h = (sea - 6.0 + continental * 24.0 + hills * 4.0
                     + mountain + detail * 0.8)
                h = max(6, min(height - 10, int(round(h))))
                heights[x + width * z] = h

                top_block = blocks.GRASS
                if h >= 50:
                    top_block = blocks.SNOW
                elif h <= sea + 1 or biomes[x + width * z] == BIOME_DESERT:
                    top_block = blocks.SAND

                for y in range(0, h + 1):
                    if y == h:
                        block = top_block
                    elif top_block == blocks.SNOW:
                        block = blocks.SNOW if y >= h - 2 else blocks.STONE
                    elif top_block == blocks.SAND:
                        block = blocks.SAND if y >= h - 2 else blocks.STONE
                    elif y >= h - 3:
                        block = blocks.DIRT
                    else:
                        block = blocks.STONE
                    grid[x + width * (z + depth * y)] = block

                # Fill lakes and the surrounding ocean.
                if h < sea:
                    water_top = sea
                    for y in range(h + 1, water_top + 1):
                        grid[x + width * (z + depth * y)] = blocks.WATER

        self.timings["height"] = time.perf_counter() - mark
        mark = time.perf_counter()

        # 2. Carve 3-D tunnels and occasional caverns.  Two intersecting
        #    isosurfaces produce connected worm-like caves rather than noisy
        #    swiss cheese.  A lower-frequency field adds room-sized pockets.
        #    Sampling on a 3-voxel lattice and carving 3x3x3 cells cuts the
        #    noise cost by roughly 4x; the fields are smooth enough that the
        #    carved volume stays almost identical at terminal resolution.
        cave_step = 3
        reach = cave_step - 1
        for z in range(2, depth - 3, cave_step):
            for x in range(2, width - 3, cave_step):
                h = heights[x + width * z]
                upper = min(h - 2, height - 2 - reach)
                for y in range(3, upper + 1, cave_step):
                    c1 = noise.noise3(x * 0.055, y * 0.075, z * 0.055)
                    c2 = noise.noise3(x * 0.105 + 31.0, y * 0.135 + 17.0,
                                      z * 0.105 - 19.0)
                    cavern = noise.noise3(x * 0.022 + 91.0, y * 0.041,
                                          z * 0.022 - 45.0)
                    if not (c1 * c1 + c2 * c2 * 1.35 < 0.0038 or cavern > 0.45):
                        continue
                    for dy in range(cave_step):
                        yy = y + dy
                        if yy > min(h - 2, height - 2):
                            continue
                        for dz in range(cave_step):
                            zz = z + dz
                            for dx in range(cave_step):
                                xx = x + dx
                                idx = xx + width * (zz + depth * yy)
                                if grid[idx] != 0 and grid[idx] != blocks.WATER:
                                    grid[idx] = blocks.AIR

        self.timings["caves"] = time.perf_counter() - mark
        mark = time.perf_counter()

        # 3. Trees.  A jittered lattice gives pleasing spacing without an
        #    expensive Poisson-disc pass.
        occupied: set[tuple[int, int]] = set()
        for gx in range(4, width - 4, 5):
            for gz in range(4, depth - 4, 5):
                x = gx + rng.randrange(-1, 2)
                z = gz + rng.randrange(-1, 2)
                if not (3 <= x < width - 3 and 3 <= z < depth - 3):
                    continue
                # Forests are dense, savanna is sparse and deserts are bare.
                biome = biomes[x + width * z]
                if biome == BIOME_FOREST:
                    density = 0.74
                elif biome == BIOME_SAVANNA:
                    density = 0.14
                elif biome == BIOME_DESERT:
                    density = 0.02
                else:
                    density = 0.30
                if rng.random() > density:
                    continue
                h = heights[x + width * z]
                if h <= sea + 1 or h >= height - 12:
                    continue
                if grid[x + width * (z + depth * h)] != blocks.GRASS:
                    continue
                # Reject steep ground.
                lo = hi = h
                for ox in (-1, 0, 1):
                    for oz in (-1, 0, 1):
                        hh = heights[(x + ox) + width * (z + oz)]
                        lo = min(lo, hh)
                        hi = max(hi, hh)
                if hi - lo > 2:
                    continue
                key = (x // 3, z // 3)
                if key in occupied:
                    continue
                occupied.add(key)
                self._grow_tree(x, h, z, rng)

        self.timings["trees"] = time.perf_counter() - mark
        mark = time.perf_counter()

        # 4. Split the dense mirror into conventional chunks and build the
        #    coarse occupancy pyramid used to skip empty air in the DDA.
        self._build_chunks()
        self.timings["chunks"] = time.perf_counter() - mark
        mark = time.perf_counter()
        self._build_macro()
        self.timings["macro"] = time.perf_counter() - mark
        mark = time.perf_counter()
        self._build_macro_top()
        self.timings["macro_top"] = time.perf_counter() - mark
        mark = time.perf_counter()
        self.spawn = self._choose_spawn()
        self.timings["spawn"] = time.perf_counter() - mark
        self.generation_time = time.perf_counter() - started
        return self

    def _grow_tree(self, x: int, ground: int, z: int, rng: random.Random) -> None:
        trunk_h = rng.randint(4, 7)
        if ground + trunk_h + 3 >= self.height:
            return
        top = ground + trunk_h
        # Canopy first, then trunk, so the trunk remains visible.
        for ly in range(top - 2, top + 2):
            radius = 2 if ly <= top else 1
            for dx in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    if abs(dx) == radius and abs(dz) == radius and rng.random() < 0.7:
                        continue
                    if rng.random() < 0.16:
                        continue
                    self._set_if_air(x + dx, ly, z + dz, blocks.LEAVES)
        for ly in range(top - 1, top + 2):
            for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                if rng.random() < 0.55:
                    self._set_if_air(x + dx, ly, z + dz, blocks.LEAVES)
        for y in range(ground + 1, top + 1):
            self.set_block(x, y, z, blocks.WOOD)

    def _set_if_air(self, x: int, y: int, z: int, block: int) -> None:
        if self.in_bounds(x, y, z) and self.get_block(x, y, z) == blocks.AIR:
            self.set_block(x, y, z, block)

    def _build_chunks(self) -> None:
        cs = CHUNK
        chunks: dict[tuple[int, int, int], bytearray] = {}
        w, d, h = self.width, self.depth, self.height
        grid = self.grid
        for cy in range(0, h, cs):
            for cz in range(0, d, cs):
                for cx in range(0, w, cs):
                    chunk = bytearray(cs * cs * cs)
                    ci = 0
                    for ly in range(cs):
                        y = cy + ly
                        for lz in range(cs):
                            z = cz + lz
                            if y >= h or z >= d:
                                ci += cs
                                continue
                            base = cx + w * (z + d * y)
                            take = min(cs, w - cx)
                            chunk[ci:ci + take] = grid[base:base + take]
                            ci += cs
                    chunks[(cx // cs, cy // cs, cz // cs)] = chunk
        self.chunks = chunks

    def _build_macro(self) -> None:
        """Mark macro regions that contain any non-air voxel."""
        ms = MACRO
        mw = (self.width + ms - 1) // ms
        md = (self.depth + ms - 1) // ms
        mh = (self.height + ms - 1) // ms
        macro = bytearray(mw * md * mh)
        grid = self.grid
        w, d, h = self.width, self.depth, self.height
        for my in range(mh):
            y0 = my * ms
            y1 = min(y0 + ms, h)
            for mz in range(md):
                z0 = mz * ms
                z1 = min(z0 + ms, d)
                for mx in range(mw):
                    x0 = mx * ms
                    x1 = min(x0 + ms, w)
                    found = 0
                    for y in range(y0, y1):
                        base = x0 + w * (z0 + d * y)
                        for z in range(z0, z1):
                            off = base + w * (z - z0)
                            for x in range(x0, x1):
                                if grid[off + (x - x0)]:
                                    found = 1
                                    break
                            if found:
                                break
                        if found:
                            break
                    macro[mx + mw * (mz + md * my)] = found
        self.macro = macro
        self.macro_dims = (mw, md, mh)

    def _build_macro_top(self) -> None:
        """Highest solid y in each 8x8 macro column.

        The renderer uses this conservative 2.5-D map for a fast sky test.
        """
        ms = self.macro_size
        mw, md, mh = self.macro_dims
        top = bytearray(mw * md)
        grid = self.grid
        w, d, h = self.width, self.depth, self.height
        macro = self.macro
        for mz in range(md):
            z0 = mz * ms
            z1 = min(z0 + ms, d)
            for mx in range(mw):
                x0 = mx * ms
                x1 = min(x0 + ms, w)
                highest = 0
                for my in range(mh - 1, -1, -1):
                    if not macro[mx + mw * (mz + md * my)]:
                        continue
                    y0 = my * ms
                    y1 = min(y0 + ms, h)
                    found = False
                    for y in range(y1 - 1, y0 - 1, -1):
                        base = x0 + w * (z0 + d * y)
                        for z in range(z0, z1):
                            off = base + w * (z - z0)
                            for x in range(x0, x1):
                                if grid[off + (x - x0)]:
                                    highest = y
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break
                    break
                top[mx + mw * mz] = highest
        self.macro_top = top

    def _choose_spawn(self) -> tuple[float, float, float, float, float]:
        w, d, sea = self.width, self.depth, self.sea_level
        cx, cz = w // 2, d // 2
        heights = self.height_map

        # Pick a high-ish vantage close to the middle, biased toward columns
        # whose neighbourhood is lower (a view over the landscape).
        best_x, best_z, best_score = cx, cz, -1e9
        for z in range(max(4, cz - 30), min(d - 4, cz + 30), 2):
            for x in range(max(4, cx - 30), min(w - 4, cx + 30), 2):
                h = heights[x + w * z]
                if h <= sea + 1:
                    continue
                around = 0.0
                for ox, oz in ((7, 0), (-7, 0), (0, 7), (0, -7)):
                    around += heights[(x + ox) + w * (z + oz)]
                canopy = 0
                for ox in (-2, 0, 2):
                    for oz in (-2, 0, 2):
                        canopy = max(canopy, self.column_top(x + ox, z + oz) - h)
                score = h * 1.5 + (around * 0.25 - h) * 0.5
                score -= canopy * 3.0
                score -= math.hypot(x - cx, z - cz) * 0.05
                if score > best_score:
                    best_x, best_z, best_score = x, z, score

        # Raise the eye above the local canopy and choose a heading that sees
        # a mixture of water, relief and open sky rather than a nearby trunk.
        local_top = 0
        for ox in range(-3, 4):
            for oz in range(-3, 4):
                local_top = max(local_top, self.column_top(best_x + ox, best_z + oz))
        cam_y = max(sea + 4.0,
                    heights[best_x + w * best_z] + 6.5,
                    local_top + 1.5)
        cam_y = min(cam_y, self.height - 3.0)

        best_yaw, best_view = 0.0, -1e9
        for k in range(32):
            angle = k * (2.0 * math.pi / 32.0)
            samples = []
            water = 0
            blocked = 0
            for dist in range(10, 105, 5):
                xx = int(best_x + math.sin(angle) * dist)
                zz = int(best_z + math.cos(angle) * dist)
                if not (0 <= xx < w and 0 <= zz < d):
                    break
                hh = heights[xx + w * zz]
                samples.append(hh)
                if hh < sea:
                    water += 1
                if dist < 34 and hh > cam_y - 1.5:
                    blocked += 1
            if not samples:
                continue
            mean = sum(samples) / len(samples)
            variance = sum((v - mean) ** 2 for v in samples) / len(samples)
            score = water * 1.35 + math.sqrt(variance) * 0.9 - blocked * 2.5
            if score > best_view:
                best_view = score
                best_yaw = angle

        return (best_x + 0.5, cam_y, best_z + 0.5, best_yaw, -0.12)

    # ---------------------------------------------------------------- helpers
    def column_top(self, x: int, z: int) -> int:
        for y in range(self.height - 1, -1, -1):
            b = self.get_block(x, y, z)
            if b not in (blocks.AIR, blocks.WATER):
                return y
        return 0
