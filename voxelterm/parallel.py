"""Optional fork-based band renderer.

The DDA inner loop is pure Python and inherently CPU-bound.  On Unix we can
fork the already-generated world into a handful of worker processes and split
the pixel rows between them.  The main process still assembles one ANSI string
and performs one stdout write per frame.
"""

from __future__ import annotations

import array
import multiprocessing as mp
import os
import signal
import sys


def _worker(conn, renderer, camera, index: int, count: int) -> None:
    # Workers never touch the terminal.  Ctrl-C is handled by the parent.
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (AttributeError, ValueError):
        pass
    rows = range(index, renderer.pixel_height, count)
    while True:
        try:
            task = conn.recv()
        except EOFError:
            break
        if task is None:
            break
        seq, x, y, z, yaw, pitch, now = task
        camera.teleport(x, y, z, yaw, pitch)
        try:
            pixels = renderer.render_rows(rows, now)
            payload = array.array("I", pixels).tobytes()
            conn.send((seq, True, payload))
        except Exception as exc:  # pragma: no cover - defensive worker path
            conn.send((seq, False, repr(exc)))


class ParallelRenderer:
    """Render interleaved pixel rows across forked worker processes."""

    def __init__(self, renderer, worker_count: int):
        self.renderer = renderer
        self.worker_count = max(1, min(worker_count, renderer.pixel_height))
        self._conns = []
        self._procs = []
        self._slices = []
        self._seq = 0
        self._ctx = mp.get_context("fork")
        self._start()

    def _start(self) -> None:
        n = self.worker_count
        # Each worker takes every n-th row.  The sky and the foreground cost
        # very different amounts, so contiguous bands would leave most workers
        # idle while the band covering the terrain did all the work.
        for k in range(n):
            parent_conn, child_conn = self._ctx.Pipe()
            proc = self._ctx.Process(
                target=_worker,
                args=(child_conn, self.renderer, self.renderer.camera, k, n),
                daemon=True,
            )
            proc.start()
            child_conn.close()
            self._conns.append(parent_conn)
            self._procs.append(proc)
            self._slices.append((k, n))

    def render(self, now: float) -> list[int]:
        cam = self.renderer.camera
        self._seq += 1
        seq = self._seq
        task = (seq, cam.x, cam.y, cam.z, cam.yaw, cam.pitch, now)
        for conn in self._conns:
            conn.send(task)
        width = self.renderer.width
        rows = self.renderer.pixel_height
        total = rows * width
        pixels = [0] * total
        for conn, (index, count) in zip(self._conns, self._slices):
            got_seq, ok, payload = conn.recv()
            if got_seq != seq or not ok:
                raise RuntimeError(f"voxel worker failed: {payload}")
            arr = array.array("I")
            arr.frombytes(payload)
            for j, row in enumerate(range(index, rows, count)):
                base = row * width
                pixels[base:base + width] = arr[j * width:(j + 1) * width]
        self.renderer.draw_entities(pixels, now)
        return pixels

    def close(self) -> None:
        for conn in self._conns:
            try:
                conn.send(None)
            except (BrokenPipeError, EOFError, OSError):
                pass
        for proc in self._procs:
            proc.join(timeout=0.4)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=0.2)
        for conn in self._conns:
            try:
                conn.close()
            except OSError:
                pass
        self._conns.clear()
        self._procs.clear()


def default_workers() -> int:
    """Reasonable worker count; leave one core for input/compositing."""
    if sys.platform == "win32" or not hasattr(os, "fork"):
        return 1
    cpus = os.cpu_count() or 1
    return max(1, min(6, cpus - 1))
