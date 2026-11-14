#!/usr/bin/env bash
# Launch the interactive ASCII voxel world.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
exec "$PYTHON" main.py "$@"
