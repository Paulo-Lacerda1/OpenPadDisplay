#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
APK="$ROOT/android/app/build/outputs/apk/debug/app-debug.apk"
SKIP_INSTALL=false
if [ "${1:-}" = "--skip-install" ]; then
    SKIP_INSTALL=true
    shift
fi
if ! command -v adb >/dev/null; then
    echo 'ADB missing. Install with: sudo apt install adb' >&2
    exit 1
fi
if [ "$SKIP_INSTALL" = false ] && [ ! -f "$APK" ]; then
    echo "Build the APK first: cd '$ROOT/android' && ./gradlew assembleDebug" >&2
    exit 1
fi
adb -d get-state
if [ "$SKIP_INSTALL" = false ]; then
    adb -d install -r "$APK"
fi
"$ROOT/scripts/usb-connect.sh"
adb -d shell am start -n org.openpaddisplay/.MainActivity
if [ "$#" -eq 0 ]; then
    set -- --width 960 --height 640 --fps 30 --bitrate 4000
fi
exec "$ROOT/scripts/server.sh" "$@"
