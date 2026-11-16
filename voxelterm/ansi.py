"""Convert a packed RGB framebuffer into one ANSI escape-code string."""

from __future__ import annotations

from .raycaster import MODE_ASCII_COLOR, MODE_ASCII_MONO, MODE_HALF

# The requested density ramp.  The leading space is the darkest value.
ASCII_RAMP = (
    " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvcz"
    "XYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
)

_BG = "\x1b[48;2;6;9;14m"
_HUD_BG = "\x1b[48;2;18;24;32m\x1b[38;2;155;185;210m"
_RESET = "\x1b[0m"

# Escape strings repeat heavily across a frame.  Cache the packed RGB -> token
# mapping so the encoder does not rebuild the same f-string thousands of times.
_FG_CACHE: dict[int, str] = {}
_BG_CACHE: dict[int, str] = {}
_CACHE_LIMIT = 32768


def _fg(rgb: int) -> str:
    token = _FG_CACHE.get(rgb)
    if token is None:
        token = f"\x1b[38;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"
        if len(_FG_CACHE) >= _CACHE_LIMIT:
            _FG_CACHE.clear()
        _FG_CACHE[rgb] = token
    return token


def _bg(rgb: int) -> str:
    token = _BG_CACHE.get(rgb)
    if token is None:
        token = f"\x1b[48;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"
        if len(_BG_CACHE) >= _CACHE_LIMIT:
            _BG_CACHE.clear()
        _BG_CACHE[rgb] = token
    return token


def _luminance(rgb: int) -> float:
    r = (rgb >> 16) & 255
    g = (rgb >> 8) & 255
    b = rgb & 255
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def encode_frame(pixels: list[int], width: int, pixel_height: int, mode: str,
                 status: str | None = None, top_pad: int = 0,
                 hud_row: int | None = None) -> str:
    """Encode pixels (top-to-bottom, packed 0xRRGGBB) as a single write buffer."""
    parts: list[str] = ["\x1b[H"]
    if top_pad > 0:
        parts.append(f"\x1b[{top_pad + 1};1H")
    ramp_last = len(ASCII_RAMP) - 1

    if mode == MODE_HALF:
        cell_rows = pixel_height // 2
        for row in range(cell_rows):
            if row:
                parts.append("\r\n")
            parts.append(_RESET)
            top_base = (row * 2) * width
            bot_base = top_base + width
            last_fg = -1
            last_bg = -1
            for x in range(width):
                top = pixels[top_base + x]
                bottom = pixels[bot_base + x]
                if top != last_fg:
                    parts.append(_fg(top))
                    last_fg = top
                if bottom != last_bg:
                    parts.append(_bg(bottom))
                    last_bg = bottom
                parts.append("\u2580")
    else:
        cell_rows = pixel_height
        mono = mode == MODE_ASCII_MONO
        mono_cache: dict[int, str] = {}
        fg_cache = _FG_CACHE
        # The background is constant for the whole ASCII frame, so set it
        # once.  Foreground runs also persist across rows; tracking one
        # `last_fg` avoids resetting and re-emitting the same colour at every
        # line boundary.
        parts.append(_RESET)
        parts.append(_BG)
        last_fg = -1
        for row in range(cell_rows):
            if row:
                parts.append("\r\n")
            base = row * width
            for x in range(width):
                rgb = pixels[base + x]
                r = (rgb >> 16) & 255
                g = (rgb >> 8) & 255
                b = rgb & 255
                tone = ((0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0) ** 0.72
                ch = ASCII_RAMP[int(tone * ramp_last + 0.5)]
                if mono:
                    v = int(58 + 190 * (tone ** 0.9))
                    if v > 255:
                        v = 255
                    if v != last_fg:
                        token = mono_cache.get(v)
                        if token is None:
                            token = f"\x1b[38;2;{v};{v};{v}m"
                            mono_cache[v] = token
                        parts.append(token)
                        last_fg = v
                else:
                    # A small lift keeps coloured glyphs legible on black.
                    r = min(255, int(r * 1.14 + 10))
                    g = min(255, int(g * 1.14 + 10))
                    b = min(255, int(b * 1.14 + 10))
                    packed = (r << 16) | (g << 8) | b
                    if packed != last_fg:
                        token = fg_cache.get(packed)
                        if token is None:
                            token = f"\x1b[38;2;{r};{g};{b}m"
                            if len(fg_cache) >= _CACHE_LIMIT:
                                fg_cache.clear()
                            fg_cache[packed] = token
                        parts.append(token)
                        last_fg = packed
                parts.append(ch)

    if status is not None:
        text = status.replace("\t", " ")
        if len(text) > width:
            text = text[:width]
        else:
            text = text.ljust(width)
        if hud_row is not None:
            parts.append(f"\x1b[{hud_row};1H")
        else:
            parts.append("\r\n")
        parts.append(_RESET)
        parts.append(_HUD_BG)
        parts.append(text)
    parts.append(_RESET)
    return "".join(parts)
