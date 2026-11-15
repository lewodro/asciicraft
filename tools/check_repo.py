#!/usr/bin/env python3
"""Check required files, README assets and relative links before shipping.

This is intentionally dependency-free and fast enough for CI. It catches the
usual repository rot: a renamed screenshot, a moved doc, a broken relative link,
or a root redirect that no longer points at the web build.

Usage: python3 tools/check_repo.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "main.py",
    "pyproject.toml",
    "run.sh",
    "serve.sh",
    "serve.bat",
    "index.html",
    "voxelterm/app.py",
    "voxelterm/ansi.py",
    "voxelterm/raycaster.py",
    "voxelterm/world.py",
    "web/index.html",
    "web/engine.js",
    "docs/ascii-rendering.md",
    "docs/launch-post.md",
    "tools/check_repo.py",
    "tools/screenshot.py",
    "assets/README.md",
    "assets/asciicraft-highlands.png",
    "assets/asciicraft-valley.png",
    "assets/asciicraft-snowline.png",
)

MARKDOWN_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "assets/README.md",
    "docs/ascii-rendering.md",
    "docs/launch-post.md",
    "web/README.md",
)

SKIP_PREFIXES = ("http://", "https://", "mailto:", "data:", "#")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
ATTR_RE = re.compile(r'(?:src|href)="([^"]+)"')
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def local_target(raw: str, source: Path):
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target or target.startswith(SKIP_PREFIXES):
        return None
    if SCHEME_RE.match(target):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    path = Path(target)
    if path.is_absolute():
        return None
    return (source.parent / path).resolve()


def main() -> int:
    errors: list[str] = []

    for name in REQUIRED:
        path = ROOT / name
        if not path.is_file():
            errors.append(f"missing required file: {name}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in REQUIRED:
        if name.startswith("assets/") and name.endswith(".png"):
            if Path(name).name not in readme:
                errors.append(f"README does not reference {Path(name).name}")

    checks = (
        ("index.html", "url=web/", "root page must redirect to web/"),
        ("web/index.html", "engine.js", "web page must load engine.js"),
        ("web/index.html", "ASCIICRAFT", "web page must use the ASCIICRAFT name"),
        ("LICENSE", "MIT License", "LICENSE must contain the MIT text"),
        ("pyproject.toml", "ASCII Minecraft", "package description is missing"),
    )
    for name, needle, message in checks:
        path = ROOT / name
        if path.is_file() and needle not in path.read_text(encoding="utf-8"):
            errors.append(f"{name}: {message}")

    checked_links = 0
    for name in MARKDOWN_FILES:
        source = ROOT / name
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8")
        candidates = LINK_RE.findall(text) + ATTR_RE.findall(text)
        for raw in candidates:
            target = local_target(raw, source)
            if target is None:
                continue
            checked_links += 1
            if not target.exists():
                errors.append(f"{name}: broken local link -> {raw}")

    if errors:
        print(f"FAIL: {len(errors)} repository problem(s)")
        for error in errors:
            print(f"  - {error}")
        return 1

    shots = len(list((ROOT / "assets").glob("*.png")))
    print(f"OK: {len(REQUIRED)} required files, "
          f"{checked_links} local links, {shots} screenshots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
