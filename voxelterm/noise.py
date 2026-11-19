"""Small, dependency-free Perlin noise implementation (2-D and 3-D)."""

from __future__ import annotations

import math
import random

_floor = math.floor

_GRAD2 = (
    (1.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0),
    (1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0),
)


def _grad3_table() -> tuple[tuple[float, float, float], ...]:
    """Expand the gradient cases into (x, y, z) coefficients once."""
    table = []
    for h in range(16):
        coeff = [0.0, 0.0, 0.0]
        coeff[0 if h < 8 else 1] = 1.0 if (h & 1) == 0 else -1.0
        if h < 4:
            axis = 1
        elif h in (12, 14):
            axis = 0
        else:
            axis = 2
        coeff[axis] += 1.0 if (h & 2) == 0 else -1.0
        table.append(tuple(coeff))
    return tuple(table)


_GRAD3 = _grad3_table()


class PerlinNoise:
    """Seeded classic Perlin noise with smooth 2-D/3-D gradients."""

    __slots__ = ("perm", "seed")

    def __init__(self, seed: int):
        self.seed = int(seed) & 0xFFFFFFFF
        rng = random.Random(self.seed)
        p = list(range(256))
        rng.shuffle(p)
        self.perm = p + p

    def noise2(self, x: float, y: float) -> float:
        p = self.perm
        fx = _floor(x)
        fy = _floor(y)
        xi = int(fx) & 255
        yi = int(fy) & 255
        xf = x - fx
        yf = y - fy
        u = xf * xf * xf * (xf * (xf * 6.0 - 15.0) + 10.0)
        v = yf * yf * yf * (yf * (yf * 6.0 - 15.0) + 10.0)

        aa = p[p[xi] + yi]
        ab = p[p[xi] + yi + 1]
        ba = p[p[xi + 1] + yi]
        bb = p[p[xi + 1] + yi + 1]

        g = _GRAD2
        ga = g[aa & 7]
        gb = g[ba & 7]
        gc = g[ab & 7]
        gd = g[bb & 7]
        x1 = ga[0] * xf + ga[1] * yf
        x2 = gb[0] * (xf - 1.0) + gb[1] * yf
        y1 = gc[0] * xf + gc[1] * (yf - 1.0)
        y2 = gd[0] * (xf - 1.0) + gd[1] * (yf - 1.0)

        xa = x1 + u * (x2 - x1)
        xb = y1 + u * (y2 - y1)
        return xa + v * (xb - xa)

    def noise3(self, x: float, y: float, z: float) -> float:
        p = self.perm
        fx = _floor(x)
        fy = _floor(y)
        fz = _floor(z)
        xi = int(fx) & 255
        yi = int(fy) & 255
        zi = int(fz) & 255
        xf = x - fx
        yf = y - fy
        zf = z - fz
        u = xf * xf * xf * (xf * (xf * 6.0 - 15.0) + 10.0)
        v = yf * yf * yf * (yf * (yf * 6.0 - 15.0) + 10.0)
        w = zf * zf * zf * (zf * (zf * 6.0 - 15.0) + 10.0)

        a = p[xi] + yi
        aa = p[a] + zi
        ab = p[a + 1] + zi
        b = p[xi + 1] + yi
        ba = p[b] + zi
        bb = p[b + 1] + zi

        g = _GRAD3
        gt = g[p[aa] & 15]
        x1 = gt[0] * xf + gt[1] * yf + gt[2] * zf
        gt = g[p[ba] & 15]
        x2 = gt[0] * (xf - 1.0) + gt[1] * yf + gt[2] * zf
        gt = g[p[ab] & 15]
        x3 = gt[0] * xf + gt[1] * (yf - 1.0) + gt[2] * zf
        gt = g[p[bb] & 15]
        x4 = gt[0] * (xf - 1.0) + gt[1] * (yf - 1.0) + gt[2] * zf
        y1 = x1 + u * (x2 - x1)
        y2 = x3 + u * (x4 - x3)
        z1 = y1 + v * (y2 - y1)

        gt = g[p[aa + 1] & 15]
        x1 = gt[0] * xf + gt[1] * yf + gt[2] * (zf - 1.0)
        gt = g[p[ba + 1] & 15]
        x2 = gt[0] * (xf - 1.0) + gt[1] * yf + gt[2] * (zf - 1.0)
        gt = g[p[ab + 1] & 15]
        x3 = gt[0] * xf + gt[1] * (yf - 1.0) + gt[2] * (zf - 1.0)
        gt = g[p[bb + 1] & 15]
        x4 = gt[0] * (xf - 1.0) + gt[1] * (yf - 1.0) + gt[2] * (zf - 1.0)
        y1 = x1 + u * (x2 - x1)
        y2 = x3 + u * (x4 - x3)
        z2 = y1 + v * (y2 - y1)

        return z1 + w * (z2 - z1)

    def fbm2(self, x: float, y: float, octaves: int = 4,
             lacunarity: float = 2.0, gain: float = 0.5) -> float:
        total = 0.0
        amp = 1.0
        freq = 1.0
        norm = 0.0
        noise = self.noise2
        for _ in range(octaves):
            total += noise(x * freq, y * freq) * amp
            norm += amp
            amp *= gain
            freq *= lacunarity
        return total / norm

    def fbm3(self, x: float, y: float, z: float, octaves: int = 3,
             lacunarity: float = 2.0, gain: float = 0.5) -> float:
        total = 0.0
        amp = 1.0
        freq = 1.0
        norm = 0.0
        noise = self.noise3
        for _ in range(octaves):
            total += noise(x * freq, y * freq, z * freq) * amp
            norm += amp
            amp *= gain
            freq *= lacunarity
        return total / norm
