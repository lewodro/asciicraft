/* Dump one engine frame as an ASCII PPM (P3) for visual/numeric comparison.
 * Usage: jsc tools/web_frame.js > frame.ppm
 */
load("web/engine.js");

var SEED = 1337;
var WIDTH = 120;
var HEIGHT = 30;

var world = new VT.World(SEED);
world.generate();
var cam = new VT.Camera(world.spawn[0], world.spawn[1], world.spawn[2],
                        world.spawn[3], world.spawn[4]);
var r = new VT.Renderer(world, cam, WIDTH, HEIGHT, "ascii-color");
var px = r.render(0.0);

var parts = ["P3", WIDTH + " " + r.pixelHeight, "255"];
for (var i = 0; i < px.length; i++) {
  var c = px[i];
  parts.push((c >> 16) & 255, (c >> 8) & 255, c & 255);
}
print(parts.join(" "));
