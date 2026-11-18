"""Voxel DDA raycasting and the procedural surface shader."""

from __future__ import annotations

import math

from . import blocks
from .world import BIOME_DESERT, BIOME_FOREST, BIOME_SAVANNA

MODE_HALF = "half"
MODE_ASCII_COLOR = "ascii-color"
MODE_ASCII_MONO = "ascii-mono"
MODES = (MODE_HALF, MODE_ASCII_COLOR, MODE_ASCII_MONO)
MODE_LABELS = {
    MODE_HALF: "HALF-BLOCK 2x",
    MODE_ASCII_COLOR: "ASCII COLOR",
    MODE_ASCII_MONO: "ASCII MONO",
}

FOG_DISTANCE = 94.0
MAX_DISTANCE = 190.0

_SKY_ZENITH = (31, 73, 151)
_SKY_HORIZON = (157, 191, 220)
_SKY_GROUND = (76, 91, 103)
# Final grade applied to lit surfaces, before fog. Exposure lifts the whole
# palette; saturation keeps grass, water and leaves vivid instead of pastel.
_EXPOSURE = 1.18
_SATURATION = 1.12
_SUN_DIR = (-0.43, 0.57, 0.70)
_SUN_LEN = math.sqrt(sum(c * c for c in _SUN_DIR))
_SUN_DIR = tuple(c / _SUN_LEN for c in _SUN_DIR)
_SUN_COLOR = (255, 239, 196)

_FACE_IDS = {
    (1, 0, 0): 1, (-1, 0, 0): 2,
    (0, 1, 0): 3, (0, -1, 0): 4,
    (0, 0, 1): 5, (0, 0, -1): 6,
}


def _hash3(a: int, b: int, c: int) -> float:
    """Fast deterministic 32-bit integer hash -> [0, 1)."""
    n = (a * 374761393 + b * 668265263 + c * 1442695041) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    n ^= n >> 16
    return (n & 0xFFFFFF) / 16777216.0


def _clamp_byte(v: float) -> int:
    if v <= 0.0:
        return 0
    if v >= 255.0:
        return 255
    return int(v + 0.5)


def _blend(c1, c2, t: float):
    inv = 1.0 - t
    return (c1[0] * inv + c2[0] * t,
            c1[1] * inv + c2[1] * t,
            c1[2] * inv + c2[2] * t)


class RaycastRenderer:
    __slots__ = (
        "world", "camera", "width", "cell_height", "mode", "pixel_height",
        "c_coeff", "a_coeff", "b_coeff",
    )

    def __init__(self, world, camera, width: int, cell_height: int, mode: str):
        self.world = world
        self.camera = camera
        self.width = max(8, int(width))
        self.cell_height = max(4, int(cell_height))
        self.mode = mode if mode in MODES else MODE_HALF
        self.pixel_height = self.cell_height * 2 if self.mode == MODE_HALF else self.cell_height
        self.c_coeff = []
        self.a_coeff = []
        self.b_coeff = []
        self._build_lut()

    def _build_lut(self) -> None:
        """Precompute camera-independent ray coefficients.

        Because the forward/right/up basis is orthonormal, a ray's inverse
        length is simply 1/sqrt(1 + a^2 + b^2).  Folding it into the pixel
        coefficients removes a square root from the per-ray hot path.
        """
        pw = self.width
        ph = self.pixel_height
        tan_h = math.tan(self.camera.fov * 0.5)
        pixel_aspect = 1.0 if self.mode == MODE_HALF else 2.0
        tan_v = tan_h * (ph / pw) * pixel_aspect
        c_list = []
        a_list = []
        b_list = []
        for py in range(ph):
            sy = (1.0 - 2.0 * (py + 0.5) / ph) * tan_v
            for px in range(pw):
                sx = (2.0 * (px + 0.5) / pw - 1.0) * tan_h
                inv = 1.0 / math.sqrt(1.0 + sx * sx + sy * sy)
                c_list.append(inv)
                a_list.append(sx * inv)
                b_list.append(sy * inv)
        self.c_coeff = c_list
        self.a_coeff = a_list
        self.b_coeff = b_list

    # ------------------------------------------------------------------- sky
    def _sky(self, dx: float, dy: float, dz: float):
        up = max(0.0, dy)
        t = up ** 0.52
        col = _blend(_SKY_HORIZON, _SKY_ZENITH, t)
        if dy < 0.0:
            col = _blend(col, _SKY_GROUND, min(1.0, -dy * 2.4))

        dot = dx * _SUN_DIR[0] + dy * _SUN_DIR[1] + dz * _SUN_DIR[2]
        if dot > 0.0:
            if dot > 0.9965:
                k = min(1.0, (dot - 0.9965) / 0.0035)
                col = _blend(col, (255, 255, 242), 0.55 + 0.45 * k)
            elif dot > 0.88:
                glow = ((dot - 0.88) / 0.1165) ** 3
                col = _blend(col, _SUN_COLOR, glow * 0.30)
        return col

    # -------------------------------------------------------------- shading
    def _ambient_occlusion(self, bx: int, by: int, bz: int,
                           nx: int, ny: int, nz: int,
                           u: float, v: float) -> float:
        eu = min(u, 1.0 - u)
        ev = min(v, 1.0 - v)
        edge = min(eu, ev)
        ao = 0.90 + 0.10 * min(1.0, edge / 0.07)

        radius = 0.17
        w = self.world
        occur_u = occur_v = occur_c = False
        su = -1 if u < 0.5 else 1
        sv = -1 if v < 0.5 else 1
        if nx:
            fx = bx + nx
            if eu < radius:
                occur_u = w.is_occluder(fx, by, bz + su)
            if ev < radius:
                occur_v = w.is_occluder(fx, by + sv, bz)
            if occur_u and occur_v:
                occur_c = w.is_occluder(fx, by + sv, bz + su)
        elif ny:
            fy = by + ny
            if eu < radius:
                occur_u = w.is_occluder(bx + su, fy, bz)
            if ev < radius:
                occur_v = w.is_occluder(bx, fy, bz + sv)
            if occur_u and occur_v:
                occur_c = w.is_occluder(bx + su, fy, bz + sv)
        else:
            fz = bz + nz
            if eu < radius:
                occur_u = w.is_occluder(bx + su, by, fz)
            if ev < radius:
                occur_v = w.is_occluder(bx, by + sv, fz)
            if occur_u and occur_v:
                occur_c = w.is_occluder(bx + su, by + sv, fz)

        if occur_u:
            ao *= 1.0 - 0.22 * (1.0 - eu / radius)
        if occur_v:
            ao *= 1.0 - 0.22 * (1.0 - ev / radius)
        if occur_c:
            ao *= 0.88
        return ao

    def _surface_color(self, block: int, nx: int, ny: int, nz: int,
                       u: float, v: float, bx: int, by: int, bz: int,
                       t: float):
        fid = _FACE_IDS.get((nx, ny, nz), 0)
        grain = _hash3(bx * 7 + int(u * 17.0) + block * 131,
                       by * 11 + int(v * 17.0) + fid * 29,
                       bz * 5 + block * 977)

        if block == blocks.GRASS:
            if ny > 0:
                base = (77, 132, 54)
                base = (base[0] + (grain - 0.5) * 20,
                        base[1] + (grain - 0.5) * 28,
                        base[2] + (grain - 0.5) * 18)
                if grain > 0.965:
                    base = (126, 150, 72)  # tiny flower/clover fleck
            elif ny < 0:
                base = (98, 71, 46)
            else:
                base = (98, 78, 54)
                if v > 0.70:
                    base = (69, 118, 49)
                    if v < 0.75:
                        base = _blend(base, (47, 82, 37), 0.40)
                    base = (base[0] + (grain - 0.5) * 16,
                            base[1] + (grain - 0.5) * 22,
                            base[2] + (grain - 0.5) * 12)
                else:
                    base = _blend(base, (67, 108, 48), 0.20)
                    base = (base[0] + (grain - 0.5) * 20,
                            base[1] + (grain - 0.5) * 16,
                            base[2] + (grain - 0.5) * 12)
            # Biome tint: forests read deeper and cooler, while savanna and
            # desert grass dries toward straw.  The pattern comes from the
            # low-frequency climate map, not per-voxel noise.
            biome = self.world.biomes[bx + self.world.width * bz]
            if biome == BIOME_FOREST:
                base = (base[0] * 0.84, base[1] * 0.96, base[2] * 0.80)
            elif biome == BIOME_SAVANNA:
                base = (min(255.0, base[0] * 1.12), base[1] * 1.02,
                        base[2] * 0.68)
            elif biome == BIOME_DESERT:
                base = (min(255.0, base[0] * 1.10), base[1] * 0.99,
                        base[2] * 0.64)
        elif block == blocks.DIRT:
            base = (104, 76, 50)
            base = (base[0] + (grain - 0.5) * 25,
                    base[1] + (grain - 0.5) * 19,
                    base[2] + (grain - 0.5) * 14)
            if grain < 0.08:
                base = (77, 54, 36)
        elif block == blocks.STONE:
            g = 0.84 + grain * 0.28
            if grain < 0.055:
                g *= 0.72
            vein = 0.5 + 0.5 * math.sin((u * 2.4 + v * 3.8 + grain) * 8.0)
            base = (105 * g, 111 * g, 116 * g)
            base = (base[0] - vein * 7, base[1] - vein * 6, base[2] - vein * 5)
        elif block == blocks.SAND:
            base = (194, 177, 126)
            base = (base[0] + (grain - 0.5) * 25,
                    base[1] + (grain - 0.5) * 23,
                    base[2] + (grain - 0.5) * 18)
        elif block == blocks.SNOW:
            g = 0.90 + grain * 0.12
            base = (228 * g, 235 * g, 244 * g)
            if grain < 0.10:
                base = (190 * g, 204 * g, 220 * g)
        elif block == blocks.PLANK:
            if ny > 0:
                g = 0.92 + grain * 0.12
                base = (176 * g, 138 * g, 92 * g)
            else:
                # Horizontal boards with a darker seam every few voxels.
                seam = 0.5 + 0.5 * math.sin(v * 24.0 + grain * 1.7)
                g = 0.84 + 0.16 * seam
                base = (158 * g, 120 * g, 78 * g)
                if grain < 0.05:
                    base = (96, 70, 45)
        elif block == blocks.CACTUS:
            if ny > 0:
                g = 0.94 + grain * 0.10
                base = (82 * g, 148 * g, 78 * g)
            else:
                ridge = 0.5 + 0.5 * math.sin(u * 26.0 + grain * 2.2)
                base = (48 + ridge * 18.0, 108 + ridge * 26.0,
                        54 + ridge * 16.0)
        elif block == blocks.ORE:
            g = 0.80 + grain * 0.26
            base = (102 * g, 97 * g, 92 * g)
            fleck = _hash3(bx * 13 + int(u * 37.0),
                           by * 17 + int(v * 37.0), bz * 19)
            if fleck > 0.58:
                base = (206, 168, 74) if fleck > 0.82 else (158, 124, 52)
        elif block == blocks.WOOD:
            if ny:
                rr = math.hypot(u - 0.5, v - 0.5)
                ring = 0.82 + 0.18 * math.sin(rr * 46.0 + grain * 3.0)
                base = (151 * ring, 116 * ring, 71 * ring)
            else:
                g = 0.82 + 0.18 * math.sin(u * 23.0 + grain * 2.5)
                base = (111 * g, 80 * g, 47 * g)
                if grain < 0.06:
                    base = (74, 51, 31)
        elif block == blocks.LEAVES:
            g = 0.76 + grain * 0.42
            base = (55 * g, 112 * g, 48 * g)
            if grain < 0.10:
                base = (35, 72, 32)
            elif grain > 0.93:
                base = (84, 145, 64)
        elif block == blocks.WATER:
            if ny > 0:
                wave = math.sin((u * 10.0 + t * 1.8) * 6.283
                                + math.sin(v * 8.0 - t * 1.3) * 2.2)
                wave2 = math.sin((v * 12.0 - t * 1.1) * 6.283 + u * 4.0)
                mix = 0.5 + 0.5 * wave * wave2
                base = _blend((35, 98, 151), (92, 164, 198), mix * 0.62)
                if mix > 0.88:
                    base = _blend(base, (188, 225, 239), (mix - 0.88) * 3.5)
            else:
                band = 0.5 + 0.5 * math.sin((v * 7.0 + t * 0.9) * 6.283)
                base = _blend((27, 79, 127), (45, 113, 161), band * 0.35)
        else:
            base = (120, 120, 120)

        # Skylight falls off below the local terrain top, so carved caves read
        # as dark rock instead of sunlit stone.  A short-range head lamp keeps
        # nearby walls readable without flattening the darkness overhead.
        w = self.world
        ground = w.height_map[bx + w.width * bz]
        if by < ground:
            shade = 1.0 - (ground - by) * 0.055
            if shade < 0.30:
                shade = 0.30
            reach = 1.0 - t / 34.0
            if reach > 0.0:
                lamp = reach * reach
                base = (base[0] + lamp * 20.0,
                        base[1] + lamp * 17.0,
                        base[2] + lamp * 10.0)
                boost = 0.52 + lamp * 0.48
                if shade < boost:
                    shade = boost
            base = (base[0] * shade, base[1] * shade, base[2] * shade)

        return base

    def _macro_entry(self, ox: float, oy: float, oz: float,
                     dx: float, dy: float, dz: float) -> float:
        """Coarse DDA: return the first distance where an occupied 8^3 cell starts."""
        world = self.world
        macro = world.macro
        mw, md, mh = world.macro_dims
        ms = world.macro_size
        mx = int(ox) // ms
        my = int(oy) // ms
        mz = int(oz) // ms
        if mx < 0 or mx >= mw or my < 0 or my >= mh or mz < 0 or mz >= md:
            return -1.0
        midx = mx + mw * (mz + md * my)
        if macro[midx]:
            return 0.0

        step_x = 1 if dx > 0.0 else -1
        step_y = 1 if dy > 0.0 else -1
        step_z = 1 if dz > 0.0 else -1
        tdx = abs(ms / dx) if dx != 0.0 else math.inf
        tdy = abs(ms / dy) if dy != 0.0 else math.inf
        tdz = abs(ms / dz) if dz != 0.0 else math.inf
        if dx > 0.0:
            tmx = ((mx + 1) * ms - ox) / dx
        elif dx < 0.0:
            tmx = (ox - mx * ms) / -dx
        else:
            tmx = math.inf
        if dy > 0.0:
            tmy = ((my + 1) * ms - oy) / dy
        elif dy < 0.0:
            tmy = (oy - my * ms) / -dy
        else:
            tmy = math.inf
        if dz > 0.0:
            tmz = ((mz + 1) * ms - oz) / dz
        elif dz < 0.0:
            tmz = (oz - mz * ms) / -dz
        else:
            tmz = math.inf

        while True:
            if tmx < tmy:
                if tmx < tmz:
                    mx += step_x
                    if mx < 0 or mx >= mw:
                        return -1.0
                    t = tmx
                    tmx += tdx
                    midx += step_x
                else:
                    mz += step_z
                    if mz < 0 or mz >= md:
                        return -1.0
                    t = tmz
                    tmz += tdz
                    midx += step_z * mw
            else:
                if tmy < tmz:
                    my += step_y
                    if my < 0 or my >= mh:
                        return -1.0
                    t = tmy
                    tmy += tdy
                    midx += step_y * mw * md
                else:
                    mz += step_z
                    if mz < 0 or mz >= md:
                        return -1.0
                    t = tmz
                    tmz += tdz
                    midx += step_z * mw
            if t > MAX_DISTANCE:
                return -1.0
            if macro[midx]:
                return t

    def _sky_clear(self, ox: float, oy: float, oz: float,
                   dx: float, dy: float, dz: float) -> bool:
        """Return True when the ray stays above every 8x8 terrain column."""
        world = self.world
        top = world.macro_top
        mw, md, _mh = world.macro_dims
        ms = world.macro_size
        mx = int(ox) // ms
        mz = int(oz) // ms
        if mx < 0 or mx >= mw or mz < 0 or mz >= md:
            return True
        step_x = 1 if dx > 0.0 else -1
        step_z = 1 if dz > 0.0 else -1
        tdx = abs(ms / dx) if dx != 0.0 else math.inf
        tdz = abs(ms / dz) if dz != 0.0 else math.inf
        if dx > 0.0:
            tmx = ((mx + 1) * ms - ox) / dx
        elif dx < 0.0:
            tmx = (ox - mx * ms) / -dx
        else:
            tmx = math.inf
        if dz > 0.0:
            tmz = ((mz + 1) * ms - oz) / dz
        elif dz < 0.0:
            tmz = (oz - mz * ms) / -dz
        else:
            tmz = math.inf

        t = 0.0
        y_here = oy
        while True:
            t_next = tmx if tmx < tmz else tmz
            if t_next > MAX_DISTANCE:
                t_next = MAX_DISTANCE
            y_next = oy + dy * t_next
            if min(y_here, y_next) <= top[mx + mw * mz] + 0.001:
                return False
            if y_next > world.height and dy >= 0.0:
                return True
            if t_next >= MAX_DISTANCE:
                return True
            if tmx < tmz:
                mx += step_x
                if mx < 0 or mx >= mw:
                    return True
                t = tmx
                tmx += tdx
            else:
                mz += step_z
                if mz < 0 or mz >= md:
                    return True
                t = tmz
                tmz += tdz
            y_here = oy + dy * t

    def _fine_segment(self, ox: float, oy: float, oz: float,
                      dx: float, dy: float, dz: float,
                      t_start: float, t_limit: float):
        """Exact DDA constrained to one occupied 8^3 macro cell."""
        world = self.world
        grid = world.grid
        W, D, H = world.width, world.depth, world.height
        t_origin = t_start + 0.00001
        sx0 = ox + dx * t_origin
        sy0 = oy + dy * t_origin
        sz0 = oz + dz * t_origin
        x = int(sx0)
        y = int(sy0)
        z = int(sz0)
        if x < 0 or x >= W or y < 0 or y >= H or z < 0 or z >= D:
            return None

        step_x = 1 if dx > 0.0 else -1
        step_y = 1 if dy > 0.0 else -1
        step_z = 1 if dz > 0.0 else -1
        tdx = abs(1.0 / dx) if dx != 0.0 else math.inf
        tdy = abs(1.0 / dy) if dy != 0.0 else math.inf
        tdz = abs(1.0 / dz) if dz != 0.0 else math.inf
        if dx > 0.0:
            tmx = (x + 1.0 - sx0) / dx
        elif dx < 0.0:
            tmx = (sx0 - x) / -dx
        else:
            tmx = math.inf
        if dy > 0.0:
            tmy = (y + 1.0 - sy0) / dy
        elif dy < 0.0:
            tmy = (sy0 - y) / -dy
        else:
            tmy = math.inf
        if dz > 0.0:
            tmz = (z + 1.0 - sz0) / dz
        elif dz < 0.0:
            tmz = (sz0 - z) / -dz
        else:
            tmz = math.inf

        idx = x + W * (z + D * y)
        block = grid[idx]
        if block:
            return (block, x, y, z, 0, 1, 0, t_start)

        while True:
            if tmx < tmy:
                if tmx < tmz:
                    x += step_x
                    if x < 0 or x >= W:
                        return None
                    idx += step_x
                    local_t = tmx
                    tmx += tdx
                    nx, ny, nz = -step_x, 0, 0
                else:
                    z += step_z
                    if z < 0 or z >= D:
                        return None
                    idx += step_z * W
                    local_t = tmz
                    tmz += tdz
                    nx, ny, nz = 0, 0, -step_z
            else:
                if tmy < tmz:
                    y += step_y
                    if y < 0 or y >= H:
                        return None
                    idx += step_y * W * D
                    local_t = tmy
                    tmy += tdy
                    nx, ny, nz = 0, -step_y, 0
                else:
                    z += step_z
                    if z < 0 or z >= D:
                        return None
                    idx += step_z * W
                    local_t = tmz
                    tmz += tdz
                    nx, ny, nz = 0, 0, -step_z
            dist = t_origin + local_t
            if dist > t_limit:
                return None
            block = grid[idx]
            if block:
                return (block, x, y, z, nx, ny, nz, dist)

    def _trace(self, ox: float, oy: float, oz: float,
               dx: float, dy: float, dz: float):
        """Hierarchical traversal: skip empty 8^3 cells, DDA inside occupied ones."""
        world = self.world
        macro = world.macro
        mw, md, mh = world.macro_dims
        ms = world.macro_size
        W, D, H = world.width, world.depth, world.height
        t = 0.0
        while t < MAX_DISTANCE:
            px = ox + dx * t
            py = oy + dy * t
            pz = oz + dz * t
            if px < 0.0 or px >= W or py < 0.0 or py >= H or pz < 0.0 or pz >= D:
                return None
            mx = int(px) // ms
            my = int(py) // ms
            mz = int(pz) // ms
            midx = mx + mw * (mz + md * my)
            if not macro[midx]:
                delta = self._macro_entry(px, py, pz, dx, dy, dz)
                if delta < 0.0:
                    return None
                t += delta + 0.00001
                continue

            # Exit distance from this macro cell.
            if dx > 0.0:
                ex = ((mx + 1) * ms - px) / dx
            elif dx < 0.0:
                ex = (px - mx * ms) / -dx
            else:
                ex = math.inf
            if dy > 0.0:
                ey = ((my + 1) * ms - py) / dy
            elif dy < 0.0:
                ey = (py - my * ms) / -dy
            else:
                ey = math.inf
            if dz > 0.0:
                ez = ((mz + 1) * ms - pz) / dz
            elif dz < 0.0:
                ez = (pz - mz * ms) / -dz
            else:
                ez = math.inf
            t_limit = t + min(ex, ey, ez)
            if t_limit > MAX_DISTANCE:
                t_limit = MAX_DISTANCE
            if t_limit <= t:
                t += 0.0001
                continue
            hit = self._fine_segment(ox, oy, oz, dx, dy, dz, t, t_limit)
            if hit is not None:
                return hit
            t = t_limit + 0.00001
        return None

    # ---------------------------------------------------------------- tracing
    def render(self, time_seconds: float = 0.0) -> list[int]:
        pixels = self.render_band(0, self.pixel_height, time_seconds)
        self.draw_entities(pixels, time_seconds)
        return pixels

    def render_band(self, y_start: int, y_end: int,
                    time_seconds: float = 0.0) -> list[int]:
        """Render a horizontal band of pixel rows (used by worker processes)."""
        cam = self.camera
        world = self.world
        grid = world.grid
        W = world.width
        D = world.depth
        H = world.height
        max_dist = MAX_DISTANCE
        fog_dist = FOG_DISTANCE
        face_light = blocks.FACE_LIGHT

        forward, right, up = cam.basis()
        fx, fy, fz = forward
        rx, ry, rz = right
        ux, uy, uz = up
        ox, oy, oz = cam.x, cam.y, cam.z

        c_arr = self.c_coeff
        a_arr = self.a_coeff
        b_arr = self.b_coeff
        y_start = max(0, min(self.pixel_height, int(y_start)))
        y_end = max(y_start, min(self.pixel_height, int(y_end)))
        start_index = y_start * self.width
        end_index = y_end * self.width
        pixels = [0] * (end_index - start_index)

        for i in range(start_index, end_index):
            c = c_arr[i]
            a = a_arr[i]
            b = b_arr[i]
            dx = fx * c + rx * a + ux * b
            dy = fy * c + ry * a + uy * b
            dz = fz * c + rz * a + uz * b

            hit = self._trace(ox, oy, oz, dx, dy, dz)
            if hit is None:
                r, g, bl = self._sky(dx, dy, dz)
                pixels[i - start_index] = (int(r) << 16) | (int(g) << 8) | int(bl)
                continue

            block, x, y, z, nx, ny, nz, dist = hit
            normal = (nx, ny, nz)
            hx = ox + dx * dist
            hy = oy + dy * dist
            hz = oz + dz * dist
            if normal[0]:
                u = hz - math.floor(hz)
                v = hy - math.floor(hy)
            elif normal[1]:
                u = hx - math.floor(hx)
                v = hz - math.floor(hz)
            else:
                u = hx - math.floor(hx)
                v = hy - math.floor(hy)
            # Guard against pathological 1.0 values at exact corners.
            if u >= 1.0:
                u = 0.999999
            if v >= 1.0:
                v = 0.999999

            color = self._surface_color(block, normal[0], normal[1], normal[2],
                                        u, v, x, y, z, time_seconds)
            light = face_light.get(normal, 0.8)
            if block != blocks.WATER:
                light *= self._ambient_occlusion(
                    x, y, z, normal[0], normal[1], normal[2], u, v)
            r = color[0] * light
            g = color[1] * light
            bl = color[2] * light

            # Stay away from the material's own luminance, then expose.
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * bl
            r = (lum + (r - lum) * _SATURATION) * _EXPOSURE
            g = (lum + (g - lum) * _SATURATION) * _EXPOSURE
            bl = (lum + (bl - lum) * _SATURATION) * _EXPOSURE

            fog = 1.0 - math.exp(-(dist / fog_dist) ** 2)
            if fog > 0.0:
                sr, sg, sb = self._sky(dx, dy, dz)
                r = r * (1.0 - fog) + sr * fog
                g = g * (1.0 - fog) + sg * fog
                bl = bl * (1.0 - fog) + sb * fog

            pixels[i - start_index] = (_clamp_byte(r) << 16) | (_clamp_byte(g) << 8) | _clamp_byte(bl)

        return pixels

    # --------------------------------------------------------------- entities
    def draw_entities(self, pixels: list[int], time_seconds: float) -> None:
        """Project orbiting birds over the finished frame with a depth test."""
        entities = self.world.entities
        if not entities:
            return
        cam = self.camera
        forward, right, up = cam.basis()
        fx, fy, fz = forward
        rx, ry, rz = right
        ux, uy, uz = up
        ox, oy, oz = cam.x, cam.y, cam.z
        pw = self.width
        ph = self.pixel_height
        tan_h = math.tan(cam.fov * 0.5)
        aspect = 1.0 if self.mode == MODE_HALF else 2.0
        tan_v = tan_h * (ph / pw) * aspect
        x_scale = pw * 0.5 / tan_h
        y_scale = ph * 0.5 / tan_v

        for bx, by, bz, orbit, spin, phase, radius in entities:
            angle = phase + time_seconds * spin
            ex = bx + math.cos(angle) * orbit
            ez = bz + math.sin(angle) * orbit
            ey = by + math.sin(time_seconds * 1.7 + phase) * 1.1
            vx = ex - ox
            vy = ey - oy
            vz = ez - oz
            depth = vx * fx + vy * fy + vz * fz
            if depth < 1.0:
                continue
            ix = int(pw * 0.5 + (vx * rx + vy * ry + vz * rz) / depth * x_scale)
            iy = int(ph * 0.5 - (vx * ux + vy * uy + vz * uz) / depth * y_scale)
            if ix < 0 or ix >= pw or iy < 0 or iy >= ph:
                continue
            length = math.sqrt(vx * vx + vy * vy + vz * vz)
            if length < 0.001 or length > 150.0:
                continue
            rdx = vx / length
            rdy = vy / length
            rdz = vz / length
            hit = self._trace(ox, oy, oz, rdx, rdy, rdz)
            if hit is not None and hit[7] < length - 0.9:
                continue

            size = radius * x_scale / depth
            n = 1 if size < 1.4 else (2 if size < 3.0 else 3)
            fog = 1.0 - math.exp(-(length / FOG_DISTANCE) ** 2)
            sr, sg, sb = self._sky(rdx, rdy, rdz)
            packed = (_clamp_byte(250.0 * (1.0 - fog) + sr * fog) << 16
                      | _clamp_byte(238.0 * (1.0 - fog) + sg * fog) << 8
                      | _clamp_byte(190.0 * (1.0 - fog) + sb * fog))
            x0 = ix - (n - 1) // 2
            y0 = iy - (n - 1) // 2
            for yy in range(y0, y0 + n):
                if yy < 0 or yy >= ph:
                    continue
                row = yy * pw
                for xx in range(x0, x0 + n):
                    if 0 <= xx < pw:
                        pixels[row + xx] = packed
