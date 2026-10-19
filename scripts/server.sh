#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/linux${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m openpaddisplay "$@"
