#!/usr/bin/env bash
# Ubuntu runtime dependencies. NVIDIA's working driver is managed by Ubuntu.
set -euo pipefail
if ! command -v apt-get >/dev/null; then
    echo 'This installer requires Ubuntu/Debian and apt-get.' >&2
    exit 1
fi
PACKAGES=(
    adb usbutils python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0
    gstreamer1.0-tools gstreamer1.0-pipewire gstreamer1.0-plugins-base
    gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly gstreamer1.0-plugins-bad
)
if [ "$#" -eq 1 ] && [ "${1:-}" = "--dry-run" ]; then
    printf 'sudo apt-get update\nsudo apt-get install --no-install-recommends'
    printf ' %q' "${PACKAGES[@]}"
    printf '\n'
    exit 0
fi
if [ "$#" -ne 0 ]; then
    echo "Usage: $0 [--dry-run]" >&2
    exit 1
fi
PRIVILEGE=()
if [ "$EUID" -ne 0 ]; then
    PRIVILEGE=(sudo)
fi
"${PRIVILEGE[@]}" apt-get update
"${PRIVILEGE[@]}" apt-get install --no-install-recommends "${PACKAGES[@]}"
echo 'Dependencies installed. Run ./scripts/doctor.sh to check NVENC availability.'
