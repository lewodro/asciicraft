/* Headless checks for web/engine.js, run with the macOS jsc shell:
 *   jsc tools/web_check.js [seed]
 * Prints JSON; tools/web_parity.py compares it with the Python implementation.
 */
load("web/engine.js");

var seed = 1337;

var rng = new VT.PyRandom(seed);
var randoms = [];
for (var i = 0; i < 6; i++) randoms.push(rng.random());
var arr = [];
for (var j = 0; j < 16; j++) arr.push(j);
rng.shuffle(arr); 
var rands = [];
for (var k = 0; k < 8; k++) rands.push(rng.randrange(-3, 7));

var world = new VT.World(seed);
world.generate();

function fnvBytes(bytes, h) {
  for (var i = 0; i < bytes.length; i++) {
    h = Math.imul(h ^ bytes[i], 16777619) >>> 0;
  }
  return h >>> 0;
}
function fnvInts(ints, h) {
  for (var i = 0; i < ints.length; i++) {
    h = Math.imul(h ^ ints[i], 16777619) >>> 0;
  }
  return h >>> 0;
}

var heightHash = fnvInts(world.heightMap, 2166136261);
var gridHash = fnvBytes(world.grid, 2166136261);

// A small ASCII frame proof: 60x18 cells using the same style mapping.
var cam = new VT.Camera(world.spawn[0], world.spawn[1], world.spawn[2],
                        world.spawn[3], world.spawn[4]);
var renderer = new VT.Renderer(world, cam, 60, 18, "ascii-color");
var pixels = renderer.render(0.0);
var counts = {};
for (var p = 0; p < pixels.length; p++) {
  var cell = VT.asciiCell(pixels[p], false);
  counts[cell[0]] = (counts[cell[0]] || 0) + 1;
}

print(JSON.stringify({
  seed: seed,
  randoms: randoms,
  shuffled: arr,
  randranges: rands,
  spawn: world.spawn,
  genTime: world.genTime,
  heightHash: heightHash,
  gridHash: gridHash,
  gridLen: world.grid.length,
  charKinds: Object.keys(counts).length,
  topChars: Object.keys(counts).sort(function (a, b) {
    return counts[b] - counts[a];
  }).slice(0, 8).join("")
}));
