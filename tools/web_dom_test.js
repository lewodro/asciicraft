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
var timeoutId = 0;
globalThis.setTimeout = function (fn, delay) {
  var wait = Number(delay);
  if (!isFinite(wait) || wait < 0) wait = 0;
  var id = ++timeoutId;
  timeouts.push({ id: id, fn: fn, at: now + wait });
  return id;
};
globalThis.clearTimeout = function (id) {
  for (var i = 0; i < timeouts.length; i++) {
    if (timeouts[i].id === id) { timeouts.splice(i, 1); return; }
  }
};

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

function earliestTimeout() {
  var best = 0;
  for (var i = 1; i < timeouts.length; i++) {
    if (timeouts[i].at < timeouts[best].at) best = i;
  }
  return best;
}

function runNextTimeout() {
  if (!timeouts.length) throw new Error("no pending timeout");
  var t = timeouts.splice(earliestTimeout(), 1)[0];
  if (t.at > now) now = t.at;
  t.fn();
  return t.at;
}

function runDueTimeouts() {
  var guard = 0;
  while (timeouts.length) {
    var i = earliestTimeout();
    if (timeouts[i].at > now) break;
    var t = timeouts.splice(i, 1)[0];
    if (++guard > 100) throw new Error("timeout loop");
    t.fn();
  }
}

function flushTimeouts() {
  var guard = 0;
  while (timeouts.length) {
    var t = timeouts.splice(earliestTimeout(), 1)[0];
    if (t.at > now) now = t.at;
    if (++guard > 100) throw new Error("timeout loop");
    t.fn();
  }
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

// --- boot: the intro card must survive a full two-second hold
var generationAt = runNextTimeout();
if (elements.overlay.classList.contains("hidden")) {
  throw new Error("overlay dismissed before the splash hold");
}
var revealAt = timeouts.length ? timeouts[earliestTimeout()].at : Infinity;
if (revealAt < 2000) {
  throw new Error("intro hold is shorter than 2s: " + revealAt + "ms");
}
dispatch("keydown", "q");
if (elements.overlay.classList.contains("hidden")) {
  throw new Error("Q dismissed the intro before the hold elapsed");
}
now = 1999;
runDueTimeouts();
if (elements.overlay.classList.contains("hidden")) {
  throw new Error("overlay dismissed before the hold elapsed");
}
runNextTimeout();
if (!elements.overlay.classList.contains("hidden")) {
  throw new Error("overlay still visible after the hold");
}
print("intro hold ok:", generationAt + "ms generation, " + revealAt + "ms reveal");
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
