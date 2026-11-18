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
        "biomes", "structures", "entities",
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
        self.structures: list[tuple[int, int, str]] = []
        self.entities: list[tuple[float, float, float, float, float, float, float]] = []

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

        # 4. Cacti give the desert biome its own silhouette.  A jittered
        #    lattice keeps them sparse; arms are added on taller stems.
        for gx in range(6, width - 6, 9):
            for gz in range(6, depth - 6, 9):
                x = gx + rng.randrange(-2, 3)
                z = gz + rng.randrange(-2, 3)
                if biomes[x + width * z] != BIOME_DESERT:
                    continue
                h = heights[x + width * z]
                if h <= sea + 1 or h >= height - 12:
                    continue
                if grid[x + width * (z + depth * h)] != blocks.SAND:
                    continue
                if rng.random() > 0.35:
                    continue
                self._grow_cactus(x, h, z, rng)
        self.timings["cacti"] = time.perf_counter() - mark
        mark = time.perf_counter()

        # 5. Cabins and ruins on flat, dry ground.  Structures are placed
        #    after trees so they can clear the site, and before the macro
        #    pyramid so the raycaster sees them immediately.
        self._place_structures(rng)
        self.timings["structures"] = time.perf_counter() - mark
        mark = time.perf_counter()

        # 6. Birds: a handful of orbiting flocks that animate from the frame
        #    time, so no per-frame entity state has to be replicated.
        self._place_entities(rng)
        self.timings["entities"] = time.perf_counter() - mark
        mark = time.perf_counter()

        # 7. Split the dense mirror into conventional chunks and build the
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
        # One bird orbits in the spawn vista so the feature reads immediately.
        sx, sy, sz, syaw, spitch = self.spawn
        sfx = math.sin(syaw) * math.cos(spitch)
        sfz = math.cos(syaw) * math.cos(spitch)
        self.entities.append((sx + sfx * 26.0, sy + 7.0, sz + sfz * 26.0,
                              4.0, 0.28, 0.0, 0.50))
        self.timings["spawn"] = time.perf_counter() - mark
        self.generation_time = time.perf_counter() - started
        return self

    def _place_structures(self, rng: random.Random) -> None:
        """Scatter a handful of cabins and ruins on buildable ground."""
        width, depth, height = self.width, self.depth, self.height
        grid = self.grid
        heights = self.height_map
        sea = self.sea_level

        for gz in range(28, depth - 28, 36):
            for gx in range(28, width - 28, 36):
                if rng.random() > 0.80:
                    continue
                cabin = rng.random() < 0.45
                half = 3 if cabin else 4
                cx = gx + rng.randrange(-9, 10)
                cz = gz + rng.randrange(-9, 10)

                lo = hi = heights[cx + width * cz]
                ok = True
                for oz in range(-half, half + 1):
                    for ox in range(-half, half + 1):
                        hh = heights[(cx + ox) + width * (cz + oz)]
                        if hh <= sea + 1 or hh >= height - 18:
                            ok = False
                            break
                        if hh < lo:
                            lo = hh
                        elif hh > hi:
                            hi = hh
                    if not ok:
                        break
                if not ok or hi - lo > 5:
                    continue

                floor = hi
                floor_block = blocks.PLANK if cabin else blocks.STONE
                # Clear and level the site (plus a one-voxel margin).  Water
                # at the margin is left alone so lakes keep their shoreline.
                for oz in range(-half - 1, half + 2):
                    for ox in range(-half - 1, half + 2):
                        x = cx + ox
                        z = cz + oz
                        hh = heights[x + width * z]
                        if hh <= sea:
                            continue
                        for y in range(hh + 1, floor + 11):
                            grid[x + width * (z + depth * y)] = blocks.AIR
                        for y in range(hh + 1, floor + 1):
                            grid[x + width * (z + depth * y)] = blocks.STONE
                        if floor > hh:
                            heights[x + width * z] = floor
                        if abs(ox) <= half and abs(oz) <= half:
                            grid[x + width * (z + depth * floor)] = floor_block

                if cabin:
                    self._build_cabin(cx, floor, cz, half)
                else:
                    self._build_ruin(cx, floor, cz, half, rng)
                self.structures.append((cx, cz, "cabin" if cabin else "ruin"))

    def _build_cabin(self, cx: int, floor: int, cz: int, half: int) -> None:
        width, depth = self.width, self.depth
        grid = self.grid
        top = floor + 4
        for y in range(floor + 1, top + 1):
            for oz in range(-half, half + 1):
                for ox in range(-half, half + 1):
                    ex = abs(ox) == half
                    ez = abs(oz) == half
                    if not (ex or ez):
                        continue
                    block = blocks.WOOD if (ex and ez) else blocks.PLANK
                    grid[(cx + ox) + width * ((cz + oz) + depth * y)] = block
        # Door on the -Z wall, windows centred on the other three.
        for y in (floor + 1, floor + 2):
            grid[cx + width * ((cz - half) + depth * y)] = blocks.AIR
        for sx in (-1, 1):
            grid[(cx + sx * half) + width * (cz + depth * (floor + 2))] = blocks.AIR
        grid[cx + width * ((cz + half) + depth * (floor + 2))] = blocks.AIR
        # Stepped pyramid roof; a stone chimney pokes through one corner.
        for step, radius in ((5, half), (6, half - 1), (7, max(1, half - 2))):
            for oz in range(-radius, radius + 1):
                for ox in range(-radius, radius + 1):
                    grid[(cx + ox) + width * ((cz + oz) + depth * (floor + step))] = blocks.PLANK
        for y in range(floor + 5, floor + 9):
            grid[(cx + half - 1) + width * ((cz + half - 1) + depth * y)] = blocks.STONE

    def _build_ruin(self, cx: int, floor: int, cz: int, half: int,
                    rng: random.Random) -> None:
        width, depth = self.width, self.depth
        grid = self.grid
        # Crumbling perimeter walls, taller toward the corners.
        for y in range(floor + 1, floor + 4):
            for oz in range(-half, half + 1):
                for ox in range(-half, half + 1):
                    if abs(ox) != half and abs(oz) != half:
                        continue
                    roll = rng.random()
                    if roll < 0.42:
                        continue
                    if roll < 0.62 and y > floor + 1:
                        continue
                    if roll < 0.78 and y > floor + 2:
                        continue
                    grid[(cx + ox) + width * ((cz + oz) + depth * y)] = blocks.STONE
        for sx in (-1, 1):
            for sz in (-1, 1):
                for y in range(floor + 1, floor + 5):
                    grid[(cx + sx * half) + width * ((cz + sz * half) + depth * y)] = blocks.STONE
        for y in (floor + 1, floor + 2):
            grid[cx + width * ((cz - half) + depth * y)] = blocks.AIR
        # Fallen rubble around the footprint.
        for _ in range(rng.randrange(5, 11)):
            ox = rng.randrange(-half - 1, half + 2)
            oz = rng.randrange(-half - 1, half + 2)
            i = (cx + ox) + width * ((cz + oz) + depth * (floor + 1))
            if grid[i] == blocks.AIR:
                grid[i] = blocks.STONE

    def _place_entities(self, rng: random.Random) -> None:
        width, depth = self.width, self.depth
        heights = self.height_map
        for _ in range(28):
            x = rng.randrange(20, width - 20)
            z = rng.randrange(20, depth - 20)
            h = heights[x + width * z]
            if h <= self.sea_level + 1:
                continue
            y = float(h + 6 + rng.randrange(0, 8))
            orbit = 3.0 + rng.random() * 5.0
            spin = (0.18 + rng.random() * 0.22)
            if rng.random() < 0.5:
                spin = -spin
            phase = rng.random() * math.tau
            radius = 0.22 + rng.random() * 0.18
            self.entities.append((float(x), y, float(z), orbit, spin, phase, radius))

    def _grow_cactus(self, x: int, ground: int, z: int,
                     rng: random.Random) -> None:
        width, depth, height = self.width, self.depth, self.height
        grid = self.grid
        tall = rng.randrange(2, 5)
        for y in range(ground + 1, ground + 1 + tall):
            if y < height:
                grid[x + width * (z + depth * y)] = blocks.CACTUS
        if tall >= 3 and rng.random() < 0.7:
            sx = 1 if rng.random() < 0.5 else -1
            ax = x + sx
            ay = ground + 2
            if 0 <= ax < width:
                i = ax + width * (z + depth * ay)
                if grid[i] == blocks.AIR:
                    grid[i] = blocks.CACTUS
                if ay + 1 < height:
                    i = ax + width * (z + depth * (ay + 1))
                    if grid[i] == blocks.AIR:
                        grid[i] = blocks.CACTUS

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
