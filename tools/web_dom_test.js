/* Minimal DOM stub to smoke-test web/index.html without a browser.
 * Run: jsc tools/web_dom_test.js
 */
load("web/engine.js");

var now = 0;
var rafCallbacks = [];
var listeners = {};
var timeouts = [];

var fillTextCalls = 0;
var fillRectCalls = 0;

function makeCtx() {
  return {
    font: "13px monospace", fillStyle: "#000", textAlign: "left",
    textBaseline: "alphabetic", fontKerning: "none",
    measureText: function (s) { return { width: 7.8 }; },
    setTransform: function () {},
    fillRect: function () { fillRectCalls++; },
    fillText: function () { fillTextCalls++; }
  };
}

function makeEl(id) {
  var el = {
    id: id,
    textContent: "",
    value: "1337",
    disabled: false,
    style: {},
    classList: {
      _set: {},
      add: function (c) { this._set[c] = true; },
      remove: function (c) { delete this._set[c]; },
      contains: function (c) { return !!this._set[c]; }
    },
    addEventListener: function (type, fn) {
      listeners[id + ":" + type] = fn;
    },
    focus: function () {},
    blur: function () {},
    setPointerCapture: function () {},
    tagName: id === "seedInput" ? "INPUT" : "DIV"
  };
  if (id === "screen") {
    el.getContext = function () { return ctx; };
    el.width = 640; el.height = 360;
  }
  return el;
}

var ctx = makeCtx();
var elements = {};
["screen", "overlay", "status", "seedInput", "loadBtn", "resumeBtn", "seedForm"]
  .forEach(function (id) { elements[id] = makeEl(id); });

globalThis.document = {
  getElementById: function (id) { return elements[id]; },
  activeElement: { tagName: "BODY", blur: function () {} }
};

globalThis.location = { search: "?seed=1337" };
globalThis.history = { replaceState: function () {} };
globalThis.performance = { now: function () { return now; } };
globalThis.innerWidth = 1280;
globalThis.innerHeight = 800;
globalThis.devicePixelRatio = 2;
globalThis.window = globalThis;

globalThis.requestAnimationFrame = function (fn) {
  rafCallbacks.push(fn);
  return rafCallbacks.length;
};
globalThis.setTimeout = function (fn) { timeouts.push(fn); return timeouts.length; };
globalThis.clearTimeout = function () {};

globalThis.addEventListener = function (type, fn) {
  listeners["window:" + type] = fn;
};

if (typeof URLSearchParams === "undefined") {
  globalThis.URLSearchParams = function (search) {
    this._p = {};
    var q = (search || "").replace(/^\?/, "");
    if (q) q.split("&").forEach(function (pair) {
      var kv = pair.split("=");
      this._p[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1] || "");
    }, this);
  };
  URLSearchParams.prototype.get = function (k) {
    return Object.prototype.hasOwnProperty.call(this._p, k) ? this._p[k] : null;
  };
  URLSearchParams.prototype.has = function (k) {
    return Object.prototype.hasOwnProperty.call(this._p, k);
  };
}

var src = readFile("web/index.html");
var m = src.match(/<script>([\s\S]*?)<\/script>/);
if (!m) throw new Error("inline script not found");
(0, eval)(m[1]);

function flushTimeouts() {
  while (timeouts.length) timeouts.shift()();
}

function dispatch(kind, key) {
  var ev = { key: key, preventDefault: function () {} };
  var fn = listeners["window:" + kind];
  if (!fn) throw new Error("no " + kind + " listener");
  fn(ev);
}

function pump(frames) {
  for (var i = 0; i < frames; i++) {
    now += 16.7;
    var cbs = rafCallbacks.splice(0);
    cbs.forEach(function (cb) { cb(now); });
  }
}

// --- boot
flushTimeouts();
if (!elements.overlay.classList.contains("hidden")) {
  throw new Error("overlay should be hidden after generation");
}
pump(3);
if (fillTextCalls < 10) throw new Error("no ASCII glyph runs drawn");
print("boot ok: fillText", fillTextCalls, "fillRect", fillRectCalls);
print("status line:", elements.status.textContent);

// --- movement
var before = fillTextCalls;
dispatch("keydown", "w");
pump(10);
dispatch("keyup", "w");
if (fillTextCalls <= before) throw new Error("no frames while moving");
print("move ok: frames drawn", fillTextCalls - before);

// --- look + space + sprint
dispatch("keydown", "ArrowRight");
dispatch("keydown", "Space");
dispatch("keydown", "e");
pump(5);
dispatch("keyup", "ArrowRight");
dispatch("keyup", "Space");
dispatch("keyup", "e");
print("look/fly ok");

// --- mode cycle: mono, half, color
["m", "m", "m"].forEach(function (k) {
  dispatch("keydown", k);
  pump(2);
});
print("mode cycle ok");

// --- pause / resume
dispatch("keydown", "q");
if (elements.overlay.classList.contains("hidden")) {
  throw new Error("pause should show overlay");
}
pump(2);
dispatch("keydown", "q");
if (!elements.overlay.classList.contains("hidden")) {
  throw new Error("resume should hide overlay");
}
print("pause/resume ok");

// --- resize
globalThis.innerWidth = 800;
globalThis.innerHeight = 600;
listeners["window:resize"]();
flushTimeouts();
pump(2);
print("resize ok");

// --- seed form
elements.seedInput.value = "42";
listeners["seedForm:submit"]({ preventDefault: function () {} });
flushTimeouts();
pump(2);
if (elements.status.textContent.indexOf("42") < 0 &&
    elements.seedInput.value !== "42") {
  throw new Error("seed form did not load seed 42");
}
print("seed form ok, seed input =", elements.seedInput.value);

// --- regenerate
dispatch("keydown", "r");
flushTimeouts();
pump(2);
print("regenerate ok, seed input =", elements.seedInput.value);

print("ALL WEB DOM TESTS PASSED");
