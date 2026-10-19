#!/usr/bin/env bash
set -euo pipefail
if ! command -v adb >/dev/null; then
    echo 'ADB missing. Install with: sudo apt install adb' >&2
    exit 1
fi
# Default to a USB device. Pass -s SERIAL when several devices are connected.
if [ "$#" -eq 0 ]; then
    set -- -d
fi
adb "$@" reverse tcp:27183 tcp:27183
adb "$@" reverse --list
