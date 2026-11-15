# Contributing to ASCIICRAFT

Thanks for taking a look. ASCIICRAFT is a small art project, so the best
contributions are focused ones: a reproducible bug, a sharper render, a faster
inner loop, or a clearer explanation.

## Ways to help

- **Report a bug** with the seed, render mode, terminal, and the exact command.
- **Share a world** by opening an issue with a screenshot and the `?seed=` URL.
- **Tune the renderer** without adding runtime dependencies.
- **Improve the docs**, especially the ASCII pipeline explanation.
- **Port it** somewhere silly: a Raspberry Pi, a VT100, a microwave display.

## Local setup

```bash
git clone https://github.com/lewodro/asciicraft.git
cd asciicraft
./run.sh --small
```

The runtime is Python 3.9+ with no third-party packages. The browser build is
plain HTML, CSS and JavaScript.

## Before opening a pull request

```bash
python3 -m py_compile main.py voxelterm/*.py tools/*.py
python3 tools/check_repo.py
python3 tools/pty_test.py --small --width 70 --height 18
python3 tools/web_parity.py
```

The JavaScript helpers need the macOS JavaScriptCore shell (`jsc`); they are
optional on other platforms. If you touch the shader, change both
`voxelterm/raycaster.py` and `web/engine.js`, then run the parity check.

## Style

- Keep the runtime dependency-free.
- Match the surrounding Python style; no formatter is enforced.
- Prefer small, readable functions over clever micro-optimisations unless the
  benchmark shows a real win.
- Keep the terminal and web shader constants in sync.
- Do not commit generated frames, `__pycache__`, or local screenshots.

## Pull requests

- One idea per pull request.
- Explain what changed and how you tested it.
- Include a screenshot for visual changes.
- Be patient. This is a side project, not a company.

By contributing, you agree that your changes are released under the MIT License.
