#!/usr/bin/env python3
"""Drive the interactive app through a pseudo-terminal and verify controls.

Usage: python3 tools/pty_test.py [--small]
Exits non-zero if the app fails to quit or prints a traceback.
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time


def run(argv: list[str], rows: int = 30, cols: int = 100) -> int:
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.environ["TERM"] = "xterm-256color"
        os.execv(sys.executable, [sys.executable, "main.py", *argv])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    out = bytearray()
    start = time.time()
    script = [
        (5.0, b""),        # let the first frames render
        (5.5, b"w"),       # move forward
        (6.0, b"w"),       # repeat in case the first lands during generation
        (6.5, b"\x1b[A"),  # look up
        (7.5, b"m"),       # ascii-color -> half
        (8.5, b"m"),       # half -> ascii mono
        (9.5, b"]"),       # raise quality
        (10.5, b"q"),      # quit
    ]
    sent = 0
    wpid, status = 0, None
    forced = False
    while True:
        now = time.time() - start
        while sent < len(script) and now >= script[sent][0]:
            if script[sent][1]:
                os.write(fd, script[sent][1])
            sent += 1
        readable, _, _ = select.select([fd], [], [], 0.05)
        if readable:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out.extend(chunk)
        wpid, status = os.waitpid(pid, os.WNOHANG)
        if wpid:
            break
        if now > 16.0:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
            wpid = -1
            forced = True
            break
    try:
        os.close(fd)
    except OSError:
        pass

    if not wpid:
        # Reading a master PTY raises EIO as the child exits; reap it now.
        for _ in range(40):
            wpid, status = os.waitpid(pid, os.WNOHANG)
            if wpid:
                break
            time.sleep(0.05)
        if not wpid:
            os.kill(pid, signal.SIGTERM)
            wpid, status = os.waitpid(pid, 0)
            forced = True

    text = out.decode("utf-8", "replace")
    frames = text.count("\x1b[H")
    print(f"frames={frames} bytes={len(out)} exit_status={status}")
    if "Traceback" in text:
        i = text.find("Traceback")
        print(text[i:i + 2000])
        return 1
    statuses = re.findall(r"(?:AC|VT)\s+[\d.]+fps \| seed \d+ \| ([A-Z ]+)", text)
    seen = []
    for mode in statuses:
        if not seen or seen[-1] != mode:
            seen.append(mode)
    print("modes:", " -> ".join(seen))
    xs = re.findall(r"x(-?\d+)/\d+ y(-?\d+) z(-?\d+)", text)
    if len(xs) > 1:
        print(f"camera: {xs[0]} -> {xs[-1]}")
        if xs[0] == xs[-1]:
            print("FAIL: camera did not move on w")
            return 1
    if forced:
        print("FAIL: app did not quit on q (had to SIGTERM)")
        return 1
    if len(seen) < 3:
        print("FAIL: mode cycle did not reach all three modes")
        return 1
    if frames < 5:
        print("FAIL: too few frames rendered")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or ["--small", "--width", "60", "--height", "16"]
    raise SystemExit(run(args))
