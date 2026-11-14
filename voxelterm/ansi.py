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


def _fg(rgb: int) -> str:
    return f"\x1b[38;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


def _bg(rgb: int) -> str:
    return f"\x1b[48;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


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
        for row in range(cell_rows):
            if row:
                parts.append("\r\n")
            parts.append(_RESET)
            parts.append(_BG)
            base = row * width
            last_fg = -1
            for x in range(width):
                rgb = pixels[base + x]
                lum = _luminance(rgb) ** 0.72
                ch = ASCII_RAMP[int(lum * ramp_last + 0.5)]
                if mono:
                    v = int(58 + 190 * (lum ** 0.9))
                    if v > 255:
                        v = 255
                    fg = mono_cache.get(v)
                    if fg is None:
                        fg = f"\x1b[38;2;{v};{v};{v}m"
                        mono_cache[v] = fg
                    if v != last_fg:
                        parts.append(fg)
                        last_fg = v
                else:
                    r = (rgb >> 16) & 255
                    g = (rgb >> 8) & 255
                    b = rgb & 255
                    # A small lift keeps coloured glyphs legible on black.
                    r = min(255, int(r * 1.10 + 8))
                    g = min(255, int(g * 1.10 + 8))
                    b = min(255, int(b * 1.10 + 8))
                    packed = (r << 16) | (g << 8) | b
                    if packed != last_fg:
                        parts.append(_fg(packed))
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
