#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Uses the installed app. Default mode: 1920×1280 at a requested 60 Hz.
exec "$ROOT/scripts/test-usb.sh" --skip-install --source virtual "$@"
