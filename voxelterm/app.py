"""Interactive terminal application and one-shot snapshot/benchmark modes."""

from __future__ import annotations

import argparse
import random
import shutil
import sys
import time

from .ansi import encode_frame
from .camera import Camera
from .parallel import ParallelRenderer, default_workers
from .raycaster import (
    MODE_ASCII_COLOR,
    MODE_ASCII_MONO,
    MODE_HALF,
    MODE_LABELS,
    MODES,
    RaycastRenderer,
)
from .terminal import CLEAR, Keyboard, TerminalSession, termios
from .world import WORLD_DEPTH, WORLD_HEIGHT, WORLD_WIDTH, World

MODE_CYCLE = (MODE_ASCII_COLOR, MODE_HALF, MODE_ASCII_MONO)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="voxelterm",
        description="Truecolor ASCII voxel world raycaster for the terminal.",
    )
    ap.add_argument("--seed", type=int, default=1337,
                    help="world seed (default: 1337)")
    ap.add_argument("--mode", choices=MODES, default=MODE_ASCII_COLOR,
                    help="initial render mode (default: ascii-color)")
    ap.add_argument("--fov", type=float, default=76.0,
                    help="horizontal field of view in degrees (default: 76)")
    ap.add_argument("--look", type=float, default=1.0,
                    help="look sensitivity multiplier; lower is slower "
                         "(default: 1.0)")
    ap.add_argument("--width", type=int, default=0,
                    help="render width in cells; 0 = terminal width")
    ap.add_argument("--height", type=int, default=0,
                    help="render height in cells; 0 = auto")
    ap.add_argument("--pixels", type=int, default=0,
                    help="approximate pixel/ray budget; 0 = automatic")
    ap.add_argument("--workers", type=int, default=0,
                    help="fork worker count; 0 = auto, 1 = serial")
    ap.add_argument("--serial", action="store_true",
                    help="disable fork-based band rendering")
    ap.add_argument("--no-hud", action="store_true",
                    help="hide the bottom status line")
    ap.add_argument("--world-width", type=int, default=0,
                    help=f"world X size (default: {WORLD_WIDTH})")
    ap.add_argument("--world-depth", type=int, default=0,
                    help=f"world Z size (default: {WORLD_DEPTH})")
    ap.add_argument("--world-height", type=int, default=0,
                    help=f"world Y size (default: {WORLD_HEIGHT})")
    ap.add_argument("--small", action="store_true",
                    help="quick 256x128x80 world for testing controls")
    ap.add_argument("--snapshot", metavar="FILE",
                    help="render one frame to an ANSI text file and exit")
    ap.add_argument("--benchmark", type=int, metavar="N", default=0,
                    help="benchmark N frames without opening the UI")
    return ap.parse_args(argv)


def world_dims(args: argparse.Namespace) -> tuple[int, int, int]:
    if args.small:
        return (256, 128, 80)
    return (
        args.world_width if args.world_width > 0 else WORLD_WIDTH,
        args.world_depth if args.world_depth > 0 else WORLD_DEPTH,
        args.world_height if args.world_height > 0 else WORLD_HEIGHT,
    )


def _new_world(seed: int, dims: tuple[int, int, int] | None = None,
               announce: bool = True) -> World:
    width, depth, height = dims or (WORLD_WIDTH, WORLD_DEPTH, WORLD_HEIGHT)
    if announce:
        print(f"Generating {width}x{depth}x{height} voxel "
              f"world (seed {seed})...", end="", flush=True)
    world = World(seed, width, depth, height).generate()
    if announce:
        print(f" done in {world.generation_time:.1f}s")
    return world


def _make_camera(world: World, fov: float) -> Camera:
    x, y, z, yaw, pitch = world.spawn
    return Camera(x, y, z, yaw, pitch, fov)


class Game:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.seed = args.seed
        self.mode = args.mode
        self.fov = args.fov
        self.look_scale = max(0.2, min(3.0, args.look))
        self.dims = world_dims(args)
        self.world = _new_world(self.seed, self.dims)
        self.camera = _make_camera(self.world, self.fov)
        self.session: TerminalSession | None = None
        self.keyboard: Keyboard | None = None
        self.renderer: RaycastRenderer | None = None
        self.par: ParallelRenderer | None = None
        self.width = 0
        self.cell_height = 0
        self.pixel_budget = args.pixels
        self.worker_count = 1 if args.serial else (
            args.workers if args.workers > 0 else default_workers())
        self.worker_count = max(1, min(12, self.worker_count))
        self.term_size = (0, 0)
        self.top_pad = 0
        self.hud_row: int | None = None
        self.running = True
        self.fps = 0.0
        self._fps_accum = 0.0
        self._fps_frames = 0
        self._last_resize = 0.0
        self._configure_renderer(start_workers=False)

    # --------------------------------------------------------------- layout
    def _configure_renderer(self, force: bool = False,
                            start_workers: bool = True) -> None:
        size = shutil.get_terminal_size((120, 40))
        cols = max(24, size.columns)
        lines = max(10, size.lines)
        width = self.args.width if self.args.width > 0 else min(cols, 220)
        width = max(24, min(300, width))
        usable = lines if self.args.no_hud else max(6, lines - 1)
        ppc = 2 if self.mode == MODE_HALF else 1
        budget = self.pixel_budget
        if budget <= 0:
            if self.worker_count > 1:
                budget = 16000 if self.mode == MODE_HALF else 10000
            else:
                budget = 4400 if self.mode == MODE_HALF else 4300
        auto_cells = max(8, budget // (width * ppc))
        if self.args.height > 0:
            cell_height = self.args.height
        else:
            cell_height = auto_cells
        cell_height = max(6, min(usable, cell_height))
        top_pad = max(0, (usable - cell_height) // 2)
        hud_row = None if self.args.no_hud else lines

        self.width = width
        self.cell_height = cell_height
        self.top_pad = top_pad
        self.hud_row = hud_row
        self.term_size = (cols, lines)

        if self.par is not None:
            self.par.close()
            self.par = None
        if self.renderer is not None:
            self.renderer = None
        renderer = RaycastRenderer(self.world, self.camera, width, cell_height,
                                   self.mode)
        self.renderer = renderer
        if self.worker_count > 1 and start_workers:
            try:
                self.par = ParallelRenderer(renderer, self.worker_count)
            except Exception:
                self.par = None
                self.worker_count = 1
        if self.session is not None and force:
            self.session.clear()

    # ------------------------------------------------------------------ frame
    def _status(self) -> str:
        cam = self.camera
        mode = MODE_LABELS[self.mode]
        workers = self.worker_count if self.par is not None else 1
        left = (f" AC {self.fps:4.1f}fps | seed {self.seed} | {mode} | "
                f"x{cam.x:.0f}/{self.world.width} y{cam.y:.0f} z{cam.z:.0f} | "
                f"{self.width}x{self.cell_height} | {workers}w")
        keys = " WASD move | arrows look | Space/C fly | E run | M mode | R seed | Q quit"
        if len(left) + len(keys) <= self.width:
            return left + keys
        if len(left) > self.width:
            return left[:self.width]
        return left

    def _render_frame(self, now: float) -> str:
        assert self.renderer is not None
        pixels = self.par.render(now) if self.par is not None else self.renderer.render(now)
        status = None if self.args.no_hud else self._status()
        return encode_frame(
            pixels, self.renderer.width, self.renderer.pixel_height, self.mode,
            status=status, top_pad=self.top_pad, hud_row=self.hud_row,
        )

    # ---------------------------------------------------------------- actions
    def _toggle_mode(self) -> None:
        idx = MODE_CYCLE.index(self.mode)
        self.mode = MODE_CYCLE[(idx + 1) % len(MODE_CYCLE)]
        self.pixel_budget = self.args.pixels
        self._configure_renderer(force=True)

    def _regenerate(self) -> None:
        assert self.session is not None
        self.running = False
        if self.par is not None:
            self.par.close()
            self.par = None
        new_seed = random.SystemRandom().randrange(0, 2 ** 31)
        w, d, _ = self.dims
        self.session.write(CLEAR + f"Generating {w}x{d} world (seed {new_seed})...")
        self.world = World(new_seed, *self.dims).generate()
        self.seed = new_seed
        self.camera = _make_camera(self.world, self.fov)
        self._configure_renderer()
        self.session.clear()
        self.running = True

    def _quality(self, direction: int) -> None:
        if self.pixel_budget <= 0:
            ppc = 2 if self.mode == MODE_HALF else 1
            self.pixel_budget = max(1000, self.width * self.cell_height * ppc)
        self.pixel_budget = int(max(1800, min(50000,
                                               self.pixel_budget * (1.22 if direction > 0 else 0.82))))
        self._configure_renderer(force=True)

    def _handle_event(self, key: str, now: float) -> None:
        if key in ("quit", "q", "escape"):
            self.running = False
        elif key == "m":
            self._toggle_mode()
        elif key == "r":
            self._regenerate()
        elif key == "[":
            self._quality(-1)
        elif key == "]":
            self._quality(1)

    # -------------------------------------------------------------------- run
    def run(self) -> None:
        try:
            with TerminalSession() as session:
                self.session = session
                self.keyboard = Keyboard(session.fd)
                self._configure_renderer(force=True)
                self._loop()
        finally:
            if self.par is not None:
                self.par.close()
                self.par = None

    def _loop(self) -> None:
        assert self.session is not None and self.keyboard is not None
        prev = time.perf_counter()
        last_resize = prev
        while self.running:
            now = time.perf_counter()
            dt = min(0.1, max(0.001, now - prev))
            prev = now

            # Events can rebuild the renderer/world, so drain first.
            for key in self.keyboard.read(now):
                self._handle_event(key, now)
            if not self.running:
                break

            if now - last_resize > 0.30:
                last_resize = now
                size = shutil.get_terminal_size((self.term_size[0], self.term_size[1]))
                if (size.columns, size.lines) != self.term_size:
                    self._configure_renderer(force=True)

            kb = self.keyboard
            cam = self.camera
            forward = (1.0 if kb.held("w", now) else 0.0) - (1.0 if kb.held("s", now) else 0.0)
            strafe = (1.0 if kb.held("d", now) else 0.0) - (1.0 if kb.held("a", now) else 0.0)
            vertical = (1.0 if kb.held("space", now) else 0.0) - (
                1.0 if (kb.held("c", now) or kb.held("x", now)) else 0.0)
            sprint = kb.held("e", now)
            cam.move(dt, forward, strafe, vertical, self.world, sprint)
            look_y = (1.0 if kb.held("right", now) else 0.0) - (1.0 if kb.held("left", now) else 0.0)
            look_p = (1.0 if kb.held("up", now) else 0.0) - (1.0 if kb.held("down", now) else 0.0)
            if look_y or look_p:
                cam.look(look_y * dt * 1.30 * self.look_scale,
                         look_p * dt * 0.95 * self.look_scale)

            t0 = time.perf_counter()
            frame = self._render_frame(now)
            self.session.write(frame)
            draw_dt = time.perf_counter() - t0
            if draw_dt > 0.0:
                self._fps_accum += draw_dt
                self._fps_frames += 1
            if self._fps_accum >= 0.25:
                measured = self._fps_frames / self._fps_accum
                self.fps = measured if self.fps == 0.0 else self.fps * 0.55 + measured * 0.45
                self._fps_accum = 0.0
                self._fps_frames = 0

            # Cap at 60 fps; never add a long sleep after a slow frame.
            spare = (1.0 / 60.0) - draw_dt
            if spare > 0.002:
                time.sleep(spare)


def _snapshot(args: argparse.Namespace) -> None:
    world = _new_world(args.seed, world_dims(args))
    cam = _make_camera(world, args.fov)
    width = args.width if args.width > 0 else 160
    height = args.height if args.height > 0 else 48
    renderer = RaycastRenderer(world, cam, width, height, args.mode)
    pixels = renderer.render(0.0)
    frame = encode_frame(pixels, renderer.width, renderer.pixel_height, args.mode)
    with open(args.snapshot, "w", encoding="utf-8") as fh:
        fh.write(frame + "\n")
    print(f"wrote {args.snapshot} ({width}x{renderer.pixel_height} pixels, "
          f"{len(frame)} bytes)")


def _benchmark(args: argparse.Namespace) -> None:
    world = _new_world(args.seed, world_dims(args))
    cam = _make_camera(world, args.fov)
    width = args.width if args.width > 0 else 160
    height = args.height if args.height > 0 else 48
    workers = 1 if args.serial else (args.workers if args.workers > 0 else default_workers())
    worker_count = max(1, min(12, workers))
    renderer = RaycastRenderer(world, cam, width, height, args.mode)
    par = None
    if worker_count > 1:
        par = ParallelRenderer(renderer, worker_count)
    frames = max(1, args.benchmark)
    renderer.render(0.0) if par is None else par.render(0.0)
    t0 = time.perf_counter()
    for i in range(frames):
        if par is not None:
            par.render(i * 0.03)
        else:
            renderer.render(i * 0.03)
    dt = time.perf_counter() - t0
    if par is not None:
        par.close()
    print(f"{frames} frames in {dt:.2f}s -> {frames / dt:.1f} FPS "
          f"({renderer.width}x{renderer.pixel_height} pixels, "
          f"{worker_count} worker{'s' if worker_count != 1 else ''}, {args.mode})")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.snapshot:
        _snapshot(args)
        return 0
    if args.benchmark:
        _benchmark(args)
        return 0
    if termios is None:
        print("voxelterm: the interactive terminal needs termios (macOS, Linux "
              "or WSL).\n  On Windows, open web/index.html for the browser "
              "version.", file=sys.stderr)
        return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("voxelterm: interactive mode needs a TTY.  Use --snapshot FILE "
              "or --benchmark N when piping output.", file=sys.stderr)
        return 2
    w, d, h = world_dims(args)
    print(
        "ASCIICRAFT - truecolor voxel world in your terminal\n"
        "  WASD move  |  arrows look  |  Space up  |  C down  |  E run\n"
        "  M render mode  |  R new seed  |  [ ] quality  |  Q quit\n"
        f"  World: {w} x {d} x {h} | about five minutes to walk across\n",
        flush=True,
    )
    try:
        Game(args).run()
    except KeyboardInterrupt:
        pass
    return 0
