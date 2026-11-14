"""Small, dependency-free Perlin noise implementation (2-D and 3-D)."""

from __future__ import annotations

import math
import random

_FADE = [0.0] * 1024
for _i in range(1024):
    _t = _i / 1023.0
    _FADE[_i] = _t * _t * _t * (_t * (_t * 6.0 - 15.0) + 10.0)

_GRAD2 = (
    (1.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0),
    (1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0),
)


def _fade(t: float) -> float:
    # 6t^5 - 15t^4 + 10t^3.  The lookup above is a fast approximation helper
    # but the polynomial is cheap and more accurate, so use it directly.
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


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
        xi = int(math.floor(x)) & 255
        yi = int(math.floor(y)) & 255
        xf = x - math.floor(x)
        yf = y - math.floor(y)
        u = _fade(xf)
        v = _fade(yf)

        aa = p[p[xi] + yi]
        ab = p[p[xi] + yi + 1]
        ba = p[p[xi + 1] + yi]
        bb = p[p[xi + 1] + yi + 1]

        g = _GRAD2
        x1 = g[aa & 7][0] * xf + g[aa & 7][1] * yf
        x2 = g[ba & 7][0] * (xf - 1.0) + g[ba & 7][1] * yf
        y1 = g[ab & 7][0] * xf + g[ab & 7][1] * (yf - 1.0)
        y2 = g[bb & 7][0] * (xf - 1.0) + g[bb & 7][1] * (yf - 1.0)

        xa = x1 + u * (x2 - x1)
        xb = y1 + u * (y2 - y1)
        return xa + v * (xb - xa)

    def _grad3(self, h: int, x: float, y: float, z: float) -> float:
        h &= 15
        u = x if h < 8 else y
        if h < 4:
            v = y
        elif h in (12, 14):
            v = x
        else:
            v = z
        return (u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v)

    def noise3(self, x: float, y: float, z: float) -> float:
        p = self.perm
        fx = math.floor(x)
        fy = math.floor(y)
        fz = math.floor(z)
        xi = int(fx) & 255
        yi = int(fy) & 255
        zi = int(fz) & 255
        xf = x - fx
        yf = y - fy
        zf = z - fz
        u = _fade(xf)
        v = _fade(yf)
        w = _fade(zf)

        a = p[xi] + yi
        aa = p[a] + zi
        ab = p[a + 1] + zi
        b = p[xi + 1] + yi
        ba = p[b] + zi
        bb = p[b + 1] + zi

        g = self._grad3
        x1 = g(p[aa], xf, yf, zf)
        x2 = g(p[ba], xf - 1.0, yf, zf)
        x3 = g(p[ab], xf, yf - 1.0, zf)
        x4 = g(p[bb], xf - 1.0, yf - 1.0, zf)
        y1 = x1 + u * (x2 - x1)
        y2 = x3 + u * (x4 - x3)
        z1 = y1 + v * (y2 - y1)

        x1 = g(p[aa + 1], xf, yf, zf - 1.0)
        x2 = g(p[ba + 1], xf - 1.0, yf, zf - 1.0)
        x3 = g(p[ab + 1], xf, yf - 1.0, zf - 1.0)
        x4 = g(p[bb + 1], xf - 1.0, yf - 1.0, zf - 1.0)
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
