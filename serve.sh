#!/usr/bin/env bash
# Serve the static web build on http://localhost:8000/web/
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-${PORT:-8000}}"
PYTHON="${PYTHON:-python3}"
echo "VOXELTERM web build: http://localhost:${PORT}/web/"
echo "Press Ctrl-C to stop."
exec "$PYTHON" -m http.server "$PORT"
