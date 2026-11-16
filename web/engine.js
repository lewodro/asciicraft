/* Voxelterm web engine - a dependency-free JS port of the Python terminal
 * world generator, camera and DDA raycaster.
 *
 * The voxel grid, Perlin noise and Python `random.Random` seeding are ported
 * exactly, so a seed produces the same terrain in the terminal app and here.
 * The shader, fog, ambient occlusion and colour palette are also shared.
 *
 * Exposes a single global: VT.
 */
(function (global) {
  "use strict";

  // ---------------------------------------------------------------- blocks
  var AIR = 0, GRASS = 1, DIRT = 2, STONE = 3, WATER = 4,
      WOOD = 5, LEAVES = 6, SAND = 7, SNOW = 8;

  // Surface biomes; mirrors world.py.
  var BIOME_PLAINS = 0, BIOME_FOREST = 1, BIOME_SAVANNA = 2, BIOME_DESERT = 3;
  var BIOME_NAMES = ["plains", "forest", "savanna", "desert"];
  var BIOME_STRIDE = 4;

  var OCCLUDERS = new Uint8Array(9);
  [GRASS, DIRT, STONE, WOOD, SAND, SNOW].forEach(function (b) { OCCLUDERS[b] = 1; });

  var FACE_LIGHT = {
    "0,1,0": 1.00, "0,-1,0": 0.44,
    "1,0,0": 0.70, "-1,0,0": 0.65,
    "0,0,1": 0.88, "0,0,-1": 0.81
  };
  // Final grade applied to lit surfaces, before fog. Mirrors raycaster.py.
  var GRADE_EXPOSURE = 1.18, GRADE_SATURATION = 1.12;

  // Same density ramp as voxelterm/ansi.py.
  var ASCII_RAMP =
    " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvcz" +
    "XYUJCLQ0OZmwqpdbkhao*#MW&8%B@$";
  var RAMP_LAST = ASCII_RAMP.length - 1;

  var WORLD_WIDTH = 1024, WORLD_DEPTH = 256, WORLD_HEIGHT = 80, SEA_LEVEL = 29;
  var CHUNK = 16, MACRO = 8;
  var FOG_DISTANCE = 94.0, MAX_DISTANCE = 190.0;

  // ------------------------------------------------------- Python random
  // MT19937 plus CPython's init_by_array / shuffle / randrange semantics.
  function PyRandom(seed) {
    this.mt = new Uint32Array(624);
    this.mti = 624;
    this.seed(seed);
  }
  PyRandom.prototype.initGenrand = function (s) {
    var mt = this.mt;
    mt[0] = s >>> 0;
    for (var i = 1; i < 624; i++) {
      mt[i] = (Math.imul(1812433253, mt[i - 1] ^ (mt[i - 1] >>> 30)) + i) >>> 0;
    }
    this.mti = 624;
  };
  PyRandom.prototype.seed = function (n) {
    var mt = this.mt, N = 624, key = n >>> 0, i = 1, j = 0, k;
    this.initGenrand(19650218);
    for (k = N; k > 0; k--) {
      mt[i] = (((mt[i] ^ Math.imul(mt[i - 1] ^ (mt[i - 1] >>> 30), 1664525)) >>> 0) + key + j) >>> 0;
      i++; j++;
      if (i >= N) { mt[0] = mt[N - 1]; i = 1; }
      if (j >= 1) j = 0;
    }
    for (k = N - 1; k > 0; k--) {
      mt[i] = (((mt[i] ^ Math.imul(mt[i - 1] ^ (mt[i - 1] >>> 30), 1566083941)) >>> 0) - i) >>> 0;
      i++;
      if (i >= N) { mt[0] = mt[N - 1]; i = 1; }
    }
    mt[0] = 0x80000000;
    this.mti = N;
  };
  PyRandom.prototype.genrand = function () {
    var mt = this.mt, N = 624, M = 397, kk, y;
    if (this.mti >= N) {
      for (kk = 0; kk < N - M; kk++) {
        y = (mt[kk] & 0x80000000) | (mt[kk + 1] & 0x7fffffff);
        mt[kk] = mt[kk + M] ^ (y >>> 1) ^ ((y & 1) ? 0x9908b0df : 0);
      }
      for (; kk < N - 1; kk++) {
        y = (mt[kk] & 0x80000000) | (mt[kk + 1] & 0x7fffffff);
        mt[kk] = mt[kk + (M - N)] ^ (y >>> 1) ^ ((y & 1) ? 0x9908b0df : 0);
      }
      y = (mt[N - 1] & 0x80000000) | (mt[0] & 0x7fffffff);
      mt[N - 1] = mt[M - 1] ^ (y >>> 1) ^ ((y & 1) ? 0x9908b0df : 0);
      this.mti = 0;
    }
    y = mt[this.mti++];
    y ^= y >>> 11;
    y ^= (y << 7) & 0x9d2c5680;
    y ^= (y << 15) & 0xefc60000;
    y ^= y >>> 18;
    return y >>> 0;
  };
  PyRandom.prototype.random = function () {
    var a = this.genrand() >>> 5, b = this.genrand() >>> 6;
    return (a * 67108864 + b) / 9007199254740992;
  };
  PyRandom.prototype.bitLength = function (n) {
    var k = 0;
    while (n > 0) { k++; n >>>= 1; }
    return k;
  };
  PyRandom.prototype.getrandbits = function (k) {
    if (k === 0) return 0;
    return this.genrand() >>> (32 - k);
  };
  PyRandom.prototype.randbelow = function (n) {
    if (n <= 0) return 0;
    var k = this.bitLength(n), r = this.getrandbits(k);
    while (r >= n) r = this.getrandbits(k);
    return r;
  };
  PyRandom.prototype.randrange = function (a, b) {
    return a + this.randbelow(b - a);
  };
  PyRandom.prototype.shuffle = function (arr) {
    for (var i = arr.length - 1; i > 0; i--) {
      var j = this.randbelow(i + 1), t = arr[i];
      arr[i] = arr[j]; arr[j] = t;
    }
  };

  // Python's round() is half-to-even; Math.round() is not.
  function pyRound(v) {
    var f = Math.floor(v), d = v - f;
    if (d > 0.5) return f + 1;
    if (d < 0.5) return f;
    return (f % 2 === 0) ? f : f + 1;
  }

  // ------------------------------------------------------------- Perlin
  var GRAD2X = [1, -1, 1, -1, 1, -1, 0, 0];
  var GRAD2Y = [1, 1, -1, -1, 0, 0, 1, -1];

  function fade(t) { return t * t * t * (t * (t * 6 - 15) + 10); }

  function PerlinNoise(seed) {
    var rng = new PyRandom(seed >>> 0);
    var p = [];
    for (var i = 0; i < 256; i++) p.push(i);
    rng.shuffle(p);
    this.perm = new Int32Array(512);
    for (var j = 0; j < 512; j++) this.perm[j] = p[j & 255];
  }

  PerlinNoise.prototype.noise2 = function (x, y) {
    var p = this.perm;
    var fx = Math.floor(x), fy = Math.floor(y);
    var xi = fx & 255, yi = fy & 255;
    var xf = x - fx, yf = y - fy;
    var u = fade(xf), v = fade(yf);
    var aa = p[p[xi] + yi], ab = p[p[xi] + yi + 1];
    var ba = p[p[xi + 1] + yi], bb = p[p[xi + 1] + yi + 1];
    var h1 = aa & 7, h2 = ba & 7, h3 = ab & 7, h4 = bb & 7;
    var x1 = GRAD2X[h1] * xf + GRAD2Y[h1] * yf;
    var x2 = GRAD2X[h2] * (xf - 1) + GRAD2Y[h2] * yf;
    var y1 = GRAD2X[h3] * xf + GRAD2Y[h3] * (yf - 1);
    var y2 = GRAD2X[h4] * (xf - 1) + GRAD2Y[h4] * (yf - 1);
    var xa = x1 + u * (x2 - x1);
    var xb = y1 + u * (y2 - y1);
    return xa + v * (xb - xa);
  };

  function grad3(h, x, y, z) {
    h &= 15;
    var u = h < 8 ? x : y;
    var v = (h < 4) ? y : ((h === 12 || h === 14) ? x : z);
    return ((h & 1) === 0 ? u : -u) + ((h & 2) === 0 ? v : -v);
  }

  PerlinNoise.prototype.noise3 = function (x, y, z) {
    var p = this.perm;
    var fx = Math.floor(x), fy = Math.floor(y), fz = Math.floor(z);
    var xi = fx & 255, yi = fy & 255, zi = fz & 255;
    var xf = x - fx, yf = y - fy, zf = z - fz;
    var u = fade(xf), v = fade(yf), w = fade(zf);
    var a = p[xi] + yi, aa = p[a] + zi, ab = p[a + 1] + zi;
    var b = p[xi + 1] + yi, ba = p[b] + zi, bb = p[b + 1] + zi;
    var x1 = grad3(p[aa], xf, yf, zf);
    var x2 = grad3(p[ba], xf - 1, yf, zf);
    var x3 = grad3(p[ab], xf, yf - 1, zf);
    var x4 = grad3(p[bb], xf - 1, yf - 1, zf);
    var y1 = x1 + u * (x2 - x1), y2 = x3 + u * (x4 - x3);
    var z1 = y1 + v * (y2 - y1);
    x1 = grad3(p[aa + 1], xf, yf, zf - 1);
    x2 = grad3(p[ba + 1], xf - 1, yf, zf - 1);
    x3 = grad3(p[ab + 1], xf, yf - 1, zf - 1);
    x4 = grad3(p[bb + 1], xf - 1, yf - 1, zf - 1);
    y1 = x1 + u * (x2 - x1); y2 = x3 + u * (x4 - x3);
    var z2 = y1 + v * (y2 - y1);
    return z1 + w * (z2 - z1);
  };

  PerlinNoise.prototype.fbm2 = function (x, y, octaves, lacunarity, gain) {
    octaves = octaves || 4; lacunarity = lacunarity || 2; gain = gain || 0.5;
    var total = 0, amp = 1, freq = 1, norm = 0;
    for (var i = 0; i < octaves; i++) {
      total += this.noise2(x * freq, y * freq) * amp;
      norm += amp; amp *= gain; freq *= lacunarity;
    }
    return total / norm;
  };

  PerlinNoise.prototype.fbm3 = function (x, y, z, octaves, lacunarity, gain) {
    octaves = octaves || 3; lacunarity = lacunarity || 2; gain = gain || 0.5;
    var total = 0, amp = 1, freq = 1, norm = 0;
    for (var i = 0; i < octaves; i++) {
      total += this.noise3(x * freq, y * freq, z * freq) * amp;
      norm += amp; amp *= gain; freq *= lacunarity;
    }
    return total / norm;
  };

  // --------------------------------------------------------------- world
  function World(seed, width, depth, height) {
    this.seed = seed >>> 0;
    this.width = width || WORLD_WIDTH;
    this.depth = depth || WORLD_DEPTH;
    this.height = height || WORLD_HEIGHT;
    this.seaLevel = SEA_LEVEL;
    this.grid = new Uint8Array(this.width * this.depth * this.height);
    this.heightMap = new Int16Array(this.width * this.depth);
    this.biomes = new Uint8Array(this.width * this.depth);
    this.spawn = [this.width * 0.5, this.height * 0.72, this.depth * 0.5, 0, 0];
    this.macro = new Uint8Array(0);
    this.macroDims = [1, 1, 1];
    this.genTime = 0;
  }

  World.prototype.index = function (x, y, z) {
    return x + this.width * (z + this.depth * y);
  };
  World.prototype.inBounds = function (x, y, z) {
    return x >= 0 && x < this.width && y >= 0 && y < this.height &&
           z >= 0 && z < this.depth;
  };
  World.prototype.get = function (x, y, z) {
    if (x >= 0 && x < this.width && y >= 0 && y < this.height &&
        z >= 0 && z < this.depth) {
      return this.grid[x + this.width * (z + this.depth * y)];
    }
    return AIR;
  };
  World.prototype.isOccluder = function (x, y, z) {
    if (x >= 0 && x < this.width && y >= 0 && y < this.height &&
        z >= 0 && z < this.depth) {
      return OCCLUDERS[this.grid[x + this.width * (z + this.depth * y)]] === 1;
    }
    return false;
  };
  World.prototype.set = function (x, y, z, block) {
    if (x >= 0 && x < this.width && y >= 0 && y < this.height &&
        z >= 0 && z < this.depth) {
      this.grid[x + this.width * (z + this.depth * y)] = block;
    }
  };
  World.prototype.setIfAir = function (x, y, z, block) {
    if (x >= 0 && x < this.width && y >= 0 && y < this.height &&
        z >= 0 && z < this.depth) {
      var i = x + this.width * (z + this.depth * y);
      if (this.grid[i] === AIR) this.grid[i] = block;
    }
  };
  World.prototype.columnTop = function (x, z) {
    for (var y = this.height - 1; y >= 0; y--) {
      var b = this.get(x, y, z);
      if (b !== AIR && b !== WATER) return y;
    }
    return 0;
  };
  World.prototype.surfaceHeight = function (x, z) {
    if (x >= 0 && x < this.width && z >= 0 && z < this.depth) {
      return this.heightMap[x + this.width * z];
    }
    return 0;
  };
  World.prototype.biomeAt = function (x, z) {
    if (x >= 0 && x < this.width && z >= 0 && z < this.depth) {
      return this.biomes[x + this.width * z];
    }
    return BIOME_PLAINS;
  };
  World.prototype.biomeName = function (x, z) {
    return BIOME_NAMES[this.biomeAt(Math.floor(x), Math.floor(z))];
  };

  World.prototype.generate = function () {
    var started = (typeof performance !== "undefined") ? performance.now() : Date.now();
    var width = this.width, depth = this.depth, height = this.height;
    var sea = this.seaLevel;
    var noise = new PerlinNoise(this.seed);
    var rng = new PyRandom(this.seed ^ 0x9E3779B9);
    var grid = this.grid, heights = this.heightMap;
    var biomes = this.biomes;
    var x, y, z, i;

    // 0. Climate map (heat x moisture), stamped on a coarse lattice.
    var stride = BIOME_STRIDE;
    for (var bz = 0; bz < depth; bz += stride) {
      for (var bx = 0; bx < width; bx += stride) {
        var heat = noise.noise2(bx * 0.0046 + 61.0, bz * 0.0046 - 37.0);
        var wet = noise.noise2(bx * 0.0063 - 23.0, bz * 0.0063 + 49.0);
        var biome;
        if (heat > 0.20 && wet < 0.10) biome = BIOME_DESERT;
        else if (wet > 0.20) biome = BIOME_FOREST;
        else if (heat > 0.10) biome = BIOME_SAVANNA;
        else biome = BIOME_PLAINS;
        var zEnd = Math.min(bz + stride, depth);
        var xEnd = Math.min(bx + stride, width);
        for (var zz = bz; zz < zEnd; zz++) {
          var row = width * zz;
          for (var xx = bx; xx < xEnd; xx++) biomes[row + xx] = biome;
        }
      }
    }

    // 1. Height field.
    for (z = 0; z < depth; z++) {
      for (x = 0; x < width; x++) {
        var wx = x + noise.noise2(x * 0.019 + 7.1, z * 0.019 - 2.3) * 9.0;
        var wz = z + noise.noise2(x * 0.019 - 4.7, z * 0.019 + 8.9) * 9.0;
        var continental = noise.fbm2(wx * 0.0074 + 11.2, wz * 0.0074 - 3.7, 5);
        var hills = noise.fbm2(x * 0.029 - 8.0, z * 0.029 + 4.0, 4);
        var ridgeField = noise.fbm2(x * 0.0112 + 21.3, z * 0.0112 - 9.1, 3);
        var ridge = Math.max(0, (1 - Math.abs(ridgeField)) - 0.65) / 0.35;
        var mountain = Math.pow(ridge, 1.8) * 28.0;
        var detail = noise.noise2(x * 0.13 + 3.0, z * 0.13 - 6.0);
        var h = sea - 6.0 + continental * 24.0 + hills * 4.0 + mountain + detail * 0.8;
        h = Math.max(6, Math.min(height - 10, pyRound(h)));
        heights[x + width * z] = h;

        var topBlock = GRASS;
        if (h >= 50) topBlock = SNOW;
        else if (h <= sea + 1 || biomes[x + width * z] === BIOME_DESERT) topBlock = SAND;

        for (y = 0; y <= h; y++) {
          var block;
          if (y === h) block = topBlock;
          else if (topBlock === SNOW) block = (y >= h - 2) ? SNOW : STONE;
          else if (topBlock === SAND) block = (y >= h - 2) ? SAND : STONE;
          else if (y >= h - 3) block = DIRT;
          else block = STONE;
          grid[x + width * (z + depth * y)] = block;
        }
        if (h < sea) {
          for (y = h + 1; y <= sea; y++) {
            grid[x + width * (z + depth * y)] = WATER;
          }
        }
      }
    }

    // 2. Caves and caverns (3-voxel lattice, 3x3x3 carve).
    var caveStep = 3, reach = caveStep - 1;
    for (z = 2; z < depth - 3; z += caveStep) {
      for (x = 2; x < width - 3; x += caveStep) {
        var hh = heights[x + width * z];
        var upper = Math.min(hh - 2, height - 2 - reach);
        for (y = 3; y <= upper; y += caveStep) {
          var c1 = noise.noise3(x * 0.055, y * 0.075, z * 0.055);
          var c2 = noise.noise3(x * 0.105 + 31.0, y * 0.135 + 17.0, z * 0.105 - 19.0);
          var cavern = noise.noise3(x * 0.022 + 91.0, y * 0.041, z * 0.022 - 45.0);
          if (!(c1 * c1 + c2 * c2 * 1.35 < 0.0038 || cavern > 0.45)) continue;
          for (var dy = 0; dy < caveStep; dy++) {
            var yy = y + dy;
            if (yy > Math.min(hh - 2, height - 2)) continue;
            for (var dz = 0; dz < caveStep; dz++) {
              var zz = z + dz;
              for (var dx = 0; dx < caveStep; dx++) {
                var xx = x + dx;
                i = xx + width * (zz + depth * yy);
                if (grid[i] !== 0 && grid[i] !== WATER) grid[i] = AIR;
              }
            }
          }
        }
      }
    }

    // 3. Trees on a jittered lattice.
    var occupied = new Set();
    for (var gx = 4; gx < width - 4; gx += 5) {
      for (var gz = 4; gz < depth - 4; gz += 5) {
        x = gx + rng.randrange(-1, 2);
        z = gz + rng.randrange(-1, 2);
        if (!(x >= 3 && x < width - 3 && z >= 3 && z < depth - 3)) continue;
        var biome = biomes[x + width * z];
        var density;
        if (biome === BIOME_FOREST) density = 0.74;
        else if (biome === BIOME_SAVANNA) density = 0.14;
        else if (biome === BIOME_DESERT) density = 0.02;
        else density = 0.30;
        if (rng.random() > density) continue;
        var gh = heights[x + width * z];
        if (gh <= sea + 1 || gh >= height - 12) continue;
        if (grid[x + width * (z + depth * gh)] !== GRASS) continue;
        var lo = gh, hi = gh;
        for (var ox = -1; ox <= 1; ox++) {
          for (var oz = -1; oz <= 1; oz++) {
            var hn = heights[(x + ox) + width * (z + oz)];
            if (hn < lo) lo = hn;
            if (hn > hi) hi = hn;
          }
        }
        if (hi - lo > 2) continue;
        var key = Math.floor(x / 3) * 4096 + Math.floor(z / 3);
        if (occupied.has(key)) continue;
        occupied.add(key);
        growTree(this, x, gh, z, rng);
      }
    }

    this.buildMacro();
    this.spawn = chooseSpawn(this);
    var ended = (typeof performance !== "undefined") ? performance.now() : Date.now();
    this.genTime = (ended - started) / 1000;
    return this;
  };

  function growTree(world, x, ground, z, rng) {
    var trunkH = rng.randrange(4, 8);
    if (ground + trunkH + 3 >= world.height) return;
    var top = ground + trunkH;
    var ly, dx, dz, radius;
    for (ly = top - 2; ly <= top + 1; ly++) {
      radius = (ly <= top) ? 2 : 1;
      for (dx = -radius; dx <= radius; dx++) {
        for (dz = -radius; dz <= radius; dz++) {
          if (Math.abs(dx) === radius && Math.abs(dz) === radius && rng.random() < 0.7) continue;
          if (rng.random() < 0.16) continue;
          world.setIfAir(x + dx, ly, z + dz, LEAVES);
        }
      }
    }
    var dirs = [[-1, 0], [1, 0], [0, -1], [0, 1]];
    for (ly = top - 1; ly <= top + 1; ly++) {
      for (var d = 0; d < 4; d++) {
        if (rng.random() < 0.55) {
          world.setIfAir(x + dirs[d][0], ly, z + dirs[d][1], LEAVES);
        }
      }
    }
    for (var y = ground + 1; y <= top; y++) world.set(x, y, z, WOOD);
  }

  World.prototype.buildMacro = function () {
    var ms = MACRO, w = this.width, d = this.depth, h = this.height;
    var mw = this.macroDims[0] = Math.ceil(w / ms);
    var md = this.macroDims[1] = Math.ceil(d / ms);
    var mh = this.macroDims[2] = Math.ceil(h / ms);
    var macro = this.macro = new Uint8Array(mw * md * mh);
    var grid = this.grid, i = 0;
    for (var y = 0; y < h; y++) {
      var my = Math.floor(y / ms) * mw * md;
      for (var z = 0; z < d; z++) {
        var mz = my + Math.floor(z / ms) * mw;
        for (var x = 0; x < w; x++, i++) {
          if (grid[i]) macro[mz + Math.floor(x / ms)] = 1;
        }
      }
    }
  };

  function chooseSpawn(world) {
    var w = world.width, d = world.depth, sea = world.seaLevel;
    var cx = Math.floor(w / 2), cz = Math.floor(d / 2);
    var heights = world.heightMap;
    var bestX = cx, bestZ = cz, bestScore = -1e9;
    var x, z, h;

    for (z = Math.max(4, cz - 30); z < Math.min(d - 4, cz + 30); z += 2) {
      for (x = Math.max(4, cx - 30); x < Math.min(w - 4, cx + 30); x += 2) {
        h = heights[x + w * z];
        if (h <= sea + 1) continue;
        var around = 0;
        around += heights[(x + 7) + w * z];
        around += heights[(x - 7) + w * z];
        around += heights[x + w * (z + 7)];
        around += heights[x + w * (z - 7)];
        var canopy = 0;
        for (var ox = -2; ox <= 2; ox += 2) {
          for (var oz = -2; oz <= 2; oz += 2) {
            canopy = Math.max(canopy, world.columnTop(x + ox, z + oz) - h);
          }
        }
        var score = h * 1.5 + (around * 0.25 - h) * 0.5;
        score -= canopy * 3.0;
        score -= Math.hypot(x - cx, z - cz) * 0.05;
        if (score > bestScore) { bestX = x; bestZ = z; bestScore = score; }
      }
    }

    var localTop = 0;
    for (var lx = -3; lx <= 3; lx++) {
      for (var lz = -3; lz <= 3; lz++) {
        localTop = Math.max(localTop, world.columnTop(bestX + lx, bestZ + lz));
      }
    }
    var camY = Math.max(sea + 4.0,
                        heights[bestX + w * bestZ] + 6.5,
                        localTop + 1.5);
    camY = Math.min(camY, world.height - 3.0);

    var bestYaw = 0, bestView = -1e9;
    for (var k = 0; k < 32; k++) {
      var angle = k * (2.0 * Math.PI / 32.0);
      var samples = [], water = 0, blocked = 0, dist;
      for (dist = 10; dist < 105; dist += 5) {
        var xx = Math.floor(bestX + Math.sin(angle) * dist);
        var zz = Math.floor(bestZ + Math.cos(angle) * dist);
        if (!(xx >= 0 && xx < w && zz >= 0 && zz < d)) break;
        var hh = heights[xx + w * zz];
        samples.push(hh);
        if (hh < sea) water++;
        if (dist < 34 && hh > camY - 1.5) blocked++;
      }
      if (!samples.length) continue;
      var mean = 0, variance = 0, m;
      for (m = 0; m < samples.length; m++) mean += samples[m];
      mean /= samples.length;
      for (m = 0; m < samples.length; m++) {
        variance += (samples[m] - mean) * (samples[m] - mean);
      }
      variance /= samples.length;
      var vscore = water * 1.35 + Math.sqrt(variance) * 0.9 - blocked * 2.5;
      if (vscore > bestView) { bestView = vscore; bestYaw = angle; }
    }
    return [bestX + 0.5, camY, bestZ + 0.5, bestYaw, -0.12];
  }

  // -------------------------------------------------------------- camera
  function Camera(x, y, z, yaw, pitch, fovDegrees) {
    this.x = x; this.y = y; this.z = z;
    this.yaw = yaw || 0; this.pitch = pitch || 0;
    this.fov = (fovDegrees || 76) * Math.PI / 180;
    this.speed = 3.4;
    this.vx = 0; this.vy = 0; this.vz = 0;
    this._basis = new Float64Array(9);
  }
  Camera.prototype.basis = function () {
    var cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    var cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    var b = this._basis;
    b[0] = sy * cp; b[1] = sp; b[2] = cy * cp;
    b[3] = cy; b[4] = 0; b[5] = -sy;
    b[6] = -sy * sp; b[7] = cp; b[8] = -cy * sp;
    return b;
  };
  Camera.prototype.move = function (dt, forward, strafe, vertical, world, sprint) {
    var mag = Math.sqrt(forward * forward + strafe * strafe + vertical * vertical);
    if (mag > 1) { forward /= mag; strafe /= mag; vertical /= mag; }
    var speed = this.speed * (sprint ? 1.8 : 1.0);
    var cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    var targetX = (sy * forward + cy * strafe) * speed;
    var targetZ = (cy * forward - sy * strafe) * speed;
    var targetY = vertical * speed;

    var response = 1 - Math.exp(-(sprint ? 16 : 12) * dt);
    this.vx += (targetX - this.vx) * response;
    this.vy += (targetY - this.vy) * response;
    this.vz += (targetZ - this.vz) * response;

    this.x += this.vx * dt;
    this.z += this.vz * dt;
    this.y += this.vy * dt;

    if (this.x < 1.2) { this.x = 1.2; this.vx = 0; }
    else if (this.x > world.width - 1.2) { this.x = world.width - 1.2; this.vx = 0; }
    if (this.z < 1.2) { this.z = 1.2; this.vz = 0; }
    else if (this.z > world.depth - 1.2) { this.z = world.depth - 1.2; this.vz = 0; }
    if (this.y < 1.2) { this.y = 1.2; this.vy = 0; }
    else if (this.y > world.height - 1.2) { this.y = world.height - 1.2; this.vy = 0; }
  };
  Camera.prototype.look = function (dyaw, dpitch) {
    this.yaw = (this.yaw + dyaw) % (2 * Math.PI);
    var limit = 88 * Math.PI / 180;
    this.pitch = Math.max(-limit, Math.min(limit, this.pitch + dpitch));
  };
  Camera.prototype.teleport = function (x, y, z, yaw, pitch) {
    this.x = x; this.y = y; this.z = z;
    this.yaw = yaw; this.pitch = pitch;
  };

  // ------------------------------------------------------------ renderer
  var SKY_ZENITH = [31, 73, 151], SKY_HORIZON = [157, 191, 220],
      SKY_GROUND = [76, 91, 103], SUN_COLOR = [255, 239, 196];
  var SUN = [-0.43, 0.57, 0.70];
  var sunLen = Math.sqrt(SUN[0] * SUN[0] + SUN[1] * SUN[1] + SUN[2] * SUN[2]);
  SUN = [SUN[0] / sunLen, SUN[1] / sunLen, SUN[2] / sunLen];

  function hash3(a, b, c) {
    var n = (Math.imul(a, 374761393) + Math.imul(b, 668265263) +
             Math.imul(c, 1442695041)) >>> 0;
    n = Math.imul(n ^ (n >>> 13), 1274126177) >>> 0;
    n ^= n >>> 16;
    return (n & 0xFFFFFF) / 16777216;
  }

  function clampByte(v) {
    if (v <= 0) return 0;
    if (v >= 255) return 255;
    return Math.floor(v + 0.5);
  }

  function Renderer(world, camera, width, cellHeight, mode) {
    this.world = world;
    this.camera = camera;
    this.width = Math.max(8, width | 0);
    this.cellHeight = Math.max(4, cellHeight | 0);
    this.mode = (mode === "half") ? "half" :
                (mode === "ascii-mono") ? "ascii-mono" : "ascii-color";
    this.pixelHeight = (this.mode === "half") ?
      this.cellHeight * 2 : this.cellHeight;
    this.pixels = new Uint32Array(this.width * this.pixelHeight);
    this._hit = new Float64Array(8);
    this._rgb = [0, 0, 0];
    this._buildLUT();
  }

  Renderer.prototype._buildLUT = function () {
    var pw = this.width, ph = this.pixelHeight;
    var tanH = Math.tan(this.camera.fov * 0.5);
    var pixelAspect = (this.mode === "half") ? 1.0 : 2.0;
    var tanV = tanH * (ph / pw) * pixelAspect;
    var n = pw * ph;
    this.cCoeff = new Float64Array(n);
    this.aCoeff = new Float64Array(n);
    this.bCoeff = new Float64Array(n);
    var i = 0;
    for (var py = 0; py < ph; py++) {
      var sy = (1.0 - 2.0 * (py + 0.5) / ph) * tanV;
      for (var px = 0; px < pw; px++) {
        var sx = (2.0 * (px + 0.5) / pw - 1.0) * tanH;
        var inv = 1.0 / Math.sqrt(1.0 + sx * sx + sy * sy);
        this.cCoeff[i] = inv;
        this.aCoeff[i] = sx * inv;
        this.bCoeff[i] = sy * inv;
        i++;
      }
    }
  };

  function blend(out, r1, g1, b1, r2, g2, b2, t) {
    var inv = 1.0 - t;
    out[0] = r1 * inv + r2 * t;
    out[1] = g1 * inv + g2 * t;
    out[2] = b1 * inv + b2 * t;
  }

  Renderer.prototype._sky = function (dx, dy, dz, out) {
    var up = Math.max(0, dy);
    var t = Math.pow(up, 0.52);
    var r = SKY_HORIZON[0] * (1 - t) + SKY_ZENITH[0] * t;
    var g = SKY_HORIZON[1] * (1 - t) + SKY_ZENITH[1] * t;
    var b = SKY_HORIZON[2] * (1 - t) + SKY_ZENITH[2] * t;
    if (dy < 0) {
      blend(out, r, g, b, SKY_GROUND[0], SKY_GROUND[1], SKY_GROUND[2],
            Math.min(1, -dy * 2.4));
      r = out[0]; g = out[1]; b = out[2];
    }
    var dot = dx * SUN[0] + dy * SUN[1] + dz * SUN[2];
    if (dot > 0) {
      if (dot > 0.9965) {
        var k = Math.min(1, (dot - 0.9965) / 0.0035);
        blend(out, r, g, b, 255, 255, 242, 0.55 + 0.45 * k);
        r = out[0]; g = out[1]; b = out[2];
      } else if (dot > 0.88) {
        var glow = Math.pow((dot - 0.88) / 0.1165, 3);
        blend(out, r, g, b, SUN_COLOR[0], SUN_COLOR[1], SUN_COLOR[2], glow * 0.30);
        r = out[0]; g = out[1]; b = out[2];
      }
    }
    out[0] = r; out[1] = g; out[2] = b;
  };

  Renderer.prototype._ao = function (bx, by, bz, nx, ny, nz, u, v) {
    var eu = Math.min(u, 1 - u), ev = Math.min(v, 1 - v);
    var edge = Math.min(eu, ev);
    var ao = 0.90 + 0.10 * Math.min(1, edge / 0.07);
    var radius = 0.17, w = this.world;
    var occurU = false, occurV = false, occurC = false;
    var su = u < 0.5 ? -1 : 1, sv = v < 0.5 ? -1 : 1;
    if (nx) {
      var fx = bx + nx;
      if (eu < radius) occurU = w.isOccluder(fx, by, bz + su);
      if (ev < radius) occurV = w.isOccluder(fx, by + sv, bz);
      if (occurU && occurV) occurC = w.isOccluder(fx, by + sv, bz + su);
    } else if (ny) {
      var fy = by + ny;
      if (eu < radius) occurU = w.isOccluder(bx + su, fy, bz);
      if (ev < radius) occurV = w.isOccluder(bx, fy, bz + sv);
      if (occurU && occurV) occurC = w.isOccluder(bx + su, fy, bz + sv);
    } else {
      var fz = bz + nz;
      if (eu < radius) occurU = w.isOccluder(bx + su, by, fz);
      if (ev < radius) occurV = w.isOccluder(bx, by + sv, fz);
      if (occurU && occurV) occurC = w.isOccluder(bx + su, by + sv, fz);
    }
    if (occurU) ao *= 1 - 0.22 * (1 - eu / radius);
    if (occurV) ao *= 1 - 0.22 * (1 - ev / radius);
    if (occurC) ao *= 0.88;
    return ao;
  };

  Renderer.prototype._surface = function (block, nx, ny, nz, u, v,
                                          bx, by, bz, t, out) {
    var fid = (nx === 1) ? 1 : (nx === -1) ? 2 : (ny === 1) ? 3 :
              (ny === -1) ? 4 : (nz === 1) ? 5 : (nz === -1) ? 6 : 0;
    var grain = hash3(bx * 7 + Math.trunc(u * 17) + block * 131,
                      by * 11 + Math.trunc(v * 17) + fid * 29,
                      bz * 5 + block * 977);
    var r = 0, g = 0, b = 0, gg;

    if (block === GRASS) {
      if (ny > 0) {
        r = 77; g = 132; b = 54;
        var dg = grain - 0.5;
        r += dg * 20; g += dg * 28; b += dg * 18;
        if (grain > 0.965) { r = 126; g = 150; b = 72; }
      } else if (ny < 0) {
        r = 98; g = 71; b = 46;
      } else {
        r = 98; g = 78; b = 54;
        if (v > 0.70) {
          r = 69; g = 118; b = 49;
          if (v < 0.75) {
            r = r + (47 - r) * 0.4; g = g + (82 - g) * 0.4; b = b + (37 - b) * 0.4;
          }
          r += (grain - 0.5) * 16; g += (grain - 0.5) * 22; b += (grain - 0.5) * 12;
        } else {
          r = r + (67 - r) * 0.2; g = g + (108 - g) * 0.2; b = b + (48 - b) * 0.2;
          r += (grain - 0.5) * 20; g += (grain - 0.5) * 16; b += (grain - 0.5) * 12;
        }
      }
      // Biome tint, mirrored from raycaster.py.
      var biome = this.world.biomes[bx + this.world.width * bz];
      if (biome === BIOME_FOREST) {
        r *= 0.84; g *= 0.96; b *= 0.80;
      } else if (biome === BIOME_SAVANNA) {
        r = Math.min(255, r * 1.12); g *= 1.02; b *= 0.68;
      } else if (biome === BIOME_DESERT) {
        r = Math.min(255, r * 1.10); g *= 0.99; b *= 0.64;
      }
    } else if (block === DIRT) {
      r = 104; g = 76; b = 50;
      r += (grain - 0.5) * 25; g += (grain - 0.5) * 19; b += (grain - 0.5) * 14;
      if (grain < 0.08) { r = 77; g = 54; b = 36; }
    } else if (block === STONE) {
      gg = 0.84 + grain * 0.28;
      if (grain < 0.055) gg *= 0.72;
      var vein = 0.5 + 0.5 * Math.sin((u * 2.4 + v * 3.8 + grain) * 8);
      r = 105 * gg - vein * 7;
      g = 111 * gg - vein * 6;
      b = 116 * gg - vein * 5;
    } else if (block === SAND) {
      r = 194; g = 177; b = 126;
      r += (grain - 0.5) * 25; g += (grain - 0.5) * 23; b += (grain - 0.5) * 18;
    } else if (block === SNOW) {
      gg = 0.90 + grain * 0.12;
      r = 228 * gg; g = 235 * gg; b = 244 * gg;
      if (grain < 0.10) { r = 190 * gg; g = 204 * gg; b = 220 * gg; }
    } else if (block === WOOD) {
      if (ny) {
        var rr = Math.hypot(u - 0.5, v - 0.5);
        var ring = 0.82 + 0.18 * Math.sin(rr * 46 + grain * 3);
        r = 151 * ring; g = 116 * ring; b = 71 * ring;
      } else {
        gg = 0.82 + 0.18 * Math.sin(u * 23 + grain * 2.5);
        r = 111 * gg; g = 80 * gg; b = 47 * gg;
        if (grain < 0.06) { r = 74; g = 51; b = 31; }
      }
    } else if (block === LEAVES) {
      gg = 0.76 + grain * 0.42;
      r = 55 * gg; g = 112 * gg; b = 48 * gg;
      if (grain < 0.10) { r = 35; g = 72; b = 32; }
      else if (grain > 0.93) { r = 84; g = 145; b = 64; }
    } else if (block === WATER) {
      if (ny > 0) {
        var wave = Math.sin((u * 10 + t * 1.8) * 6.283 +
                            Math.sin(v * 8 - t * 1.3) * 2.2);
        var wave2 = Math.sin((v * 12 - t * 1.1) * 6.283 + u * 4);
        var mix = 0.5 + 0.5 * wave * wave2;
        blend(out, 35, 98, 151, 92, 164, 198, mix * 0.62);
        r = out[0]; g = out[1]; b = out[2];
        if (mix > 0.88) {
          blend(out, r, g, b, 188, 225, 239, (mix - 0.88) * 3.5);
          r = out[0]; g = out[1]; b = out[2];
        }
      } else {
        var band = 0.5 + 0.5 * Math.sin((v * 7 + t * 0.9) * 6.283);
        blend(out, 27, 79, 127, 45, 113, 161, band * 0.35);
        r = out[0]; g = out[1]; b = out[2];
      }
    } else {
      r = 120; g = 120; b = 120;
    }
    out[0] = r; out[1] = g; out[2] = b;
  };

  Renderer.prototype._macroEntry = function (ox, oy, oz, dx, dy, dz) {
    var world = this.world, macro = world.macro;
    var mw = world.macroDims[0], md = world.macroDims[1], mh = world.macroDims[2];
    var ms = MACRO;
    var mx = Math.floor(ox / ms), my = Math.floor(oy / ms), mz = Math.floor(oz / ms);
    if (mx < 0 || mx >= mw || my < 0 || my >= mh || mz < 0 || mz >= md) return -1;
    var midx = mx + mw * (mz + md * my);
    if (macro[midx]) return 0;

    var stepX = dx > 0 ? 1 : -1, stepY = dy > 0 ? 1 : -1, stepZ = dz > 0 ? 1 : -1;
    var tdx = dx !== 0 ? Math.abs(ms / dx) : Infinity;
    var tdy = dy !== 0 ? Math.abs(ms / dy) : Infinity;
    var tdz = dz !== 0 ? Math.abs(ms / dz) : Infinity;
    var tmx, tmy, tmz;
    if (dx > 0) tmx = ((mx + 1) * ms - ox) / dx;
    else if (dx < 0) tmx = (ox - mx * ms) / -dx;
    else tmx = Infinity;
    if (dy > 0) tmy = ((my + 1) * ms - oy) / dy;
    else if (dy < 0) tmy = (oy - my * ms) / -dy;
    else tmy = Infinity;
    if (dz > 0) tmz = ((mz + 1) * ms - oz) / dz;
    else if (dz < 0) tmz = (oz - mz * ms) / -dz;
    else tmz = Infinity;

    for (;;) {
      var tt;
      if (tmx < tmy) {
        if (tmx < tmz) {
          mx += stepX;
          if (mx < 0 || mx >= mw) return -1;
          tt = tmx; tmx += tdx; midx += stepX;
        } else {
          mz += stepZ;
          if (mz < 0 || mz >= md) return -1;
          tt = tmz; tmz += tdz; midx += stepZ * mw;
        }
      } else {
        if (tmy < tmz) {
          my += stepY;
          if (my < 0 || my >= mh) return -1;
          tt = tmy; tmy += tdy; midx += stepY * mw * md;
        } else {
          mz += stepZ;
          if (mz < 0 || mz >= md) return -1;
          tt = tmz; tmz += tdz; midx += stepZ * mw;
        }
      }
      if (tt > MAX_DISTANCE) return -1;
      if (macro[midx]) return tt;
    }
  };

  Renderer.prototype._fine = function (ox, oy, oz, dx, dy, dz,
                                       tStart, tLimit, out) {
    var world = this.world, grid = world.grid;
    var W = world.width, D = world.depth, H = world.height;
    var tOrigin = tStart + 0.00001;
    var sx0 = ox + dx * tOrigin, sy0 = oy + dy * tOrigin, sz0 = oz + dz * tOrigin;
    var x = Math.trunc(sx0), y = Math.trunc(sy0), z = Math.trunc(sz0);
    if (x < 0 || x >= W || y < 0 || y >= H || z < 0 || z >= D) return false;

    var stepX = dx > 0 ? 1 : -1, stepY = dy > 0 ? 1 : -1, stepZ = dz > 0 ? 1 : -1;
    var tdx = dx !== 0 ? Math.abs(1 / dx) : Infinity;
    var tdy = dy !== 0 ? Math.abs(1 / dy) : Infinity;
    var tdz = dz !== 0 ? Math.abs(1 / dz) : Infinity;
    var tmx, tmy, tmz;
    if (dx > 0) tmx = (x + 1 - sx0) / dx;
    else if (dx < 0) tmx = (sx0 - x) / -dx;
    else tmx = Infinity;
    if (dy > 0) tmy = (y + 1 - sy0) / dy;
    else if (dy < 0) tmy = (sy0 - y) / -dy;
    else tmy = Infinity;
    if (dz > 0) tmz = (z + 1 - sz0) / dz;
    else if (dz < 0) tmz = (sz0 - z) / -dz;
    else tmz = Infinity;

    var idx = x + W * (z + D * y);
    var block = grid[idx];
    if (block) {
      out[0] = block; out[1] = x; out[2] = y; out[3] = z;
      out[4] = 0; out[5] = 1; out[6] = 0; out[7] = tStart;
      return true;
    }
    for (;;) {
      var localT, nx = 0, ny = 0, nz = 0;
      if (tmx < tmy) {
        if (tmx < tmz) {
          x += stepX;
          if (x < 0 || x >= W) return false;
          idx += stepX; localT = tmx; tmx += tdx; nx = -stepX;
        } else {
          z += stepZ;
          if (z < 0 || z >= D) return false;
          idx += stepZ * W; localT = tmz; tmz += tdz; nz = -stepZ;
        }
      } else {
        if (tmy < tmz) {
          y += stepY;
          if (y < 0 || y >= H) return false;
          idx += stepY * W * D; localT = tmy; tmy += tdy; ny = -stepY;
        } else {
          z += stepZ;
          if (z < 0 || z >= D) return false;
          idx += stepZ * W; localT = tmz; tmz += tdz; nz = -stepZ;
        }
      }
      var dist = tOrigin + localT;
      if (dist > tLimit) return false;
      block = grid[idx];
      if (block) {
        out[0] = block; out[1] = x; out[2] = y; out[3] = z;
        out[4] = nx; out[5] = ny; out[6] = nz; out[7] = dist;
        return true;
      }
    }
  };

  Renderer.prototype._trace = function (ox, oy, oz, dx, dy, dz, out) {
    var world = this.world, macro = world.macro;
    var mw = world.macroDims[0], md = world.macroDims[1];
    var ms = MACRO, W = world.width, D = world.depth, H = world.height;
    var t = 0;
    while (t < MAX_DISTANCE) {
      var px = ox + dx * t, py = oy + dy * t, pz = oz + dz * t;
      if (px < 0 || px >= W || py < 0 || py >= H || pz < 0 || pz >= D) return false;
      var mx = Math.floor(px / ms), my = Math.floor(py / ms), mz = Math.floor(pz / ms);
      var midx = mx + mw * (mz + md * my);
      if (!macro[midx]) {
        var delta = this._macroEntry(px, py, pz, dx, dy, dz);
        if (delta < 0) return false;
        t += delta + 0.00001;
        continue;
      }
      var ex, ey, ez;
      if (dx > 0) ex = ((mx + 1) * ms - px) / dx;
      else if (dx < 0) ex = (px - mx * ms) / -dx;
      else ex = Infinity;
      if (dy > 0) ey = ((my + 1) * ms - py) / dy;
      else if (dy < 0) ey = (py - my * ms) / -dy;
      else ey = Infinity;
      if (dz > 0) ez = ((mz + 1) * ms - pz) / dz;
      else if (dz < 0) ez = (pz - mz * ms) / -dz;
      else ez = Infinity;
      var tLimit = t + Math.min(ex, ey, ez);
      if (tLimit > MAX_DISTANCE) tLimit = MAX_DISTANCE;
      if (tLimit <= t) { t += 0.0001; continue; }
      if (this._fine(ox, oy, oz, dx, dy, dz, t, tLimit, out)) return true;
      t = tLimit + 0.00001;
    }
    return false;
  };

  Renderer.prototype.render = function (timeSeconds) {
    var t = timeSeconds || 0;
    var cam = this.camera, world = this.world;
    var b = cam.basis();
    var fx = b[0], fy = b[1], fz = b[2];
    var rx = b[3], ry = b[4], rz = b[5];
    var ux = b[6], uy = b[7], uz = b[8];
    var ox = cam.x, oy = cam.y, oz = cam.z;
    var W = this.width, ph = this.pixelHeight;
    var pixels = this.pixels;
    var hit = this._hit, rgb = this._rgb;
    var cArr = this.cCoeff, aArr = this.aCoeff, bArr = this.bCoeff;

    for (var i = 0, n = W * ph; i < n; i++) {
      var c = cArr[i], a = aArr[i], bb = bArr[i];
      var dx = fx * c + rx * a + ux * bb;
      var dy = fy * c + ry * a + uy * bb;
      var dz = fz * c + rz * a + uz * bb;

      if (!this._trace(ox, oy, oz, dx, dy, dz, hit)) {
        this._sky(dx, dy, dz, rgb);
        pixels[i] = (Math.trunc(rgb[0]) << 16) | (Math.trunc(rgb[1]) << 8) |
                    Math.trunc(rgb[2]);
        continue;
      }

      var block = hit[0], x = hit[1], y = hit[2], z = hit[3];
      var nx = hit[4], ny = hit[5], nz = hit[6], dist = hit[7];
      var hx = ox + dx * dist, hy = oy + dy * dist, hz = oz + dz * dist;
      var u, v;
      if (nx) { u = hz - Math.floor(hz); v = hy - Math.floor(hy); }
      else if (ny) { u = hx - Math.floor(hx); v = hz - Math.floor(hz); }
      else { u = hx - Math.floor(hx); v = hy - Math.floor(hy); }
      if (u >= 1) u = 0.999999;
      if (v >= 1) v = 0.999999;

      this._surface(block, nx, ny, nz, u, v, x, y, z, t, rgb);
      var r = rgb[0], g = rgb[1], bl = rgb[2];
      var light = FACE_LIGHT[nx + "," + ny + "," + nz];
      if (light === undefined) light = 0.8;
      if (block !== WATER) light *= this._ao(x, y, z, nx, ny, nz, u, v);
      r *= light; g *= light; bl *= light;

      var lum = 0.2126 * r + 0.7152 * g + 0.0722 * bl;
      r = (lum + (r - lum) * GRADE_SATURATION) * GRADE_EXPOSURE;
      g = (lum + (g - lum) * GRADE_SATURATION) * GRADE_EXPOSURE;
      bl = (lum + (bl - lum) * GRADE_SATURATION) * GRADE_EXPOSURE;

      var fog = 1 - Math.exp(-Math.pow(dist / FOG_DISTANCE, 2));
      if (fog > 0) {
        this._sky(dx, dy, dz, rgb);
        r = r * (1 - fog) + rgb[0] * fog;
        g = g * (1 - fog) + rgb[1] * fog;
        bl = bl * (1 - fog) + rgb[2] * fog;
      }
      pixels[i] = (clampByte(r) << 16) | (clampByte(g) << 8) | clampByte(bl);
    }
    return pixels;
  };

  // ------------------------------------------------------- ASCII style map
  function luminance(rgb) {
    var r = (rgb >> 16) & 255, g = (rgb >> 8) & 255, b = rgb & 255;
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  }

  function asciiCell(rgb, mono) {
    var lum = Math.pow(luminance(rgb), 0.72);
    var idx = Math.floor(lum * RAMP_LAST + 0.5);
    var ch = ASCII_RAMP.charAt(idx);
    var r, g, b;
    if (mono) {
      var v = Math.floor(58 + 190 * Math.pow(lum, 0.9));
      if (v > 255) v = 255;
      r = g = b = v;
    } else {
      r = ((rgb >> 16) & 255);
      g = ((rgb >> 8) & 255);
      b = (rgb & 255);
      r = Math.min(255, Math.floor(r * 1.14 + 10));
      g = Math.min(255, Math.floor(g * 1.14 + 10));
      b = Math.min(255, Math.floor(b * 1.14 + 10));
    }
    return [ch, r, g, b];
  }

  global.VT = {
    AIR: AIR, GRASS: GRASS, DIRT: DIRT, STONE: STONE, WATER: WATER,
    WOOD: WOOD, LEAVES: LEAVES, SAND: SAND, SNOW: SNOW,
    WORLD_WIDTH: WORLD_WIDTH, WORLD_DEPTH: WORLD_DEPTH,
    WORLD_HEIGHT: WORLD_HEIGHT, SEA_LEVEL: SEA_LEVEL,
    ASCII_RAMP: ASCII_RAMP,
    PyRandom: PyRandom, PerlinNoise: PerlinNoise,
    World: World, Camera: Camera, Renderer: Renderer,
    generateWorld: function (seed, width, depth, height) {
      return new World(seed, width, depth, height).generate();
    },
    asciiCell: asciiCell,
    luminance: luminance
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
