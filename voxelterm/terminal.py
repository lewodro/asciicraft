"""Raw terminal handling and a repeat-aware keyboard state machine."""

from __future__ import annotations

import errno
import os
import select
import sys

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - Windows fallback is intentionally small
    termios = None
    tty = None


ALT_ON = "\x1b[?1049h"
ALT_OFF = "\x1b[?1049l"
CURSOR_HIDE = "\x1b[?25l"
CURSOR_SHOW = "\x1b[?25h"
WRAP_OFF = "\x1b[?7l"
WRAP_ON = "\x1b[?7h"
CLEAR = "\x1b[2J\x1b[H"
RESET = "\x1b[0m"


class TerminalSession:
    """Put stdin into raw mode and manage the alternate screen."""

    def __init__(self):
        self.fd = None
        self.old_attrs = None
        self.active = False

    def __enter__(self):
        if not sys.stdin.isatty() or termios is None:
            raise RuntimeError("voxelterm needs an interactive Unix-style terminal")
        self.fd = sys.stdin.fileno()
        self.old_attrs = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        self.active = True
        self.write(ALT_ON + CURSOR_HIDE + WRAP_OFF + CLEAR)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.active:
            try:
                self.write(RESET + CURSOR_SHOW + WRAP_ON + ALT_OFF)
            finally:
                if self.old_attrs is not None:
                    termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_attrs)
                self.active = False
        return False

    def write(self, text: str) -> None:
        # Bypass the text wrapper so each frame is encoded and written once.
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            buffer.write(text.encode("utf-8", "replace"))
            buffer.flush()
        else:  # pragma: no cover - unusual stdout replacement
            sys.stdout.write(text)
            sys.stdout.flush()

    def clear(self) -> None:
        self.write(CLEAR)


class Keyboard:
    """Tracks held keys even though terminals only report key-down events.

    Auto-repeat keeps refreshing the deadline.  The first press gets a longer
    deadline to bridge the OS's initial repeat delay; this makes movement feel
    smooth in ordinary terminals.
    """

    def __init__(self, fd: int | None = None):
        self.fd = fd
        self.until: dict[str, float] = {}
        self.last: dict[str, float] = {}
        self.buffer = bytearray()
        self._escape_at = -1.0
        self.shift_until = 0.0

    def press(self, key: str, now: float) -> None:
        previous = self.last.get(key, -100.0)
        bridge = 0.42 if now - previous > 0.20 else 0.15
        self.until[key] = now + bridge
        self.last[key] = now

    def release(self, key: str) -> None:
        self.until[key] = 0.0

    def held(self, key: str, now: float) -> bool:
        return self.until.get(key, 0.0) > now

    def shift_held(self, now: float) -> bool:
        return self.shift_until > now

    def read(self, now: float) -> list[str]:
        if self.fd is None:
            return []
        events: list[str] = []
        try:
            readable, _, _ = select.select([self.fd], [], [], 0.0)
        except (OSError, ValueError):
            return events
        if not readable:
            # A lone Escape (or a truncated CSI sequence) produces no more
            # input; flush it once the ambiguous window has passed.
            if (self.buffer and self.buffer[0] == 27 and self._escape_at >= 0.0
                    and now - self._escape_at > 0.20):
                return self._parse(now)
            return events
        try:
            chunk = os.read(self.fd, 8192)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return events
            raise
        if chunk:
            self.buffer.extend(chunk)
        if self.buffer:
            events.extend(self._parse(now))
        return events

    def _parse(self, now: float) -> list[str]:
        buf = self.buffer
        events: list[str] = []
        while buf:
            b = buf[0]
            if b == 3 or b == 4:  # Ctrl-C / Ctrl-D
                events.append("quit")
                del buf[0]
                continue
            if b == 27:
                if self._escape_at < 0.0:
                    self._escape_at = now
                if len(buf) >= 2 and buf[1] in (ord("["), ord("O")):
                    # Find the final byte of the CSI/SS3 sequence.
                    end = -1
                    for i in range(2, min(len(buf), 16)):
                        if 0x40 <= buf[i] <= 0x7E:
                            end = i
                            break
                    if end < 0:
                        if now - self._escape_at > 0.20:
                            drop = 2 if len(buf) >= 2 and buf[1] in (
                                ord("["), ord("O")) else 1
                            del buf[:drop]
                            self._escape_at = -1.0
                            events.append("escape")
                            continue
                        break
                    seq = bytes(buf[2:end + 1])
                    del buf[:end + 1]
                    self._escape_at = -1.0
                    final = seq[-1:]
                    params = seq[:-1].decode("ascii", "ignore")
                    if final in (b"A", b"B", b"C", b"D"):
                        direction = {b"A": "up", b"B": "down",
                                     b"C": "right", b"D": "left"}[final]
                        if ";2" in params or params.startswith("1;2"):
                            self.shift_until = now + 0.3
                        self.press(direction, now)
                        events.append(direction)
                    continue
                # Alt+key, a lone Escape, or an unrecognised sequence.
                if len(buf) > 1:
                    del buf[0]
                    self._escape_at = -1.0
                    continue
                if now - self._escape_at > 0.20:
                    del buf[0]
                    self._escape_at = -1.0
                    events.append("escape")
                    continue
                break

            # Decode a single printable ASCII key.
            if 32 <= b < 127:
                ch = chr(b)
                if ch.isupper() and ch.isalpha():
                    self.shift_until = now + 0.35
                key = ch.lower()
                if key == " ":
                    key = "space"
                elif key in ("\r", "\n"):
                    key = "enter"
                self.press(key, now)
                events.append(key)
                del buf[0]
                continue
            if b in (10, 13):
                events.append("enter")
            del buf[0]
        return events
