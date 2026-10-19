# OpenPadDisplay

An open-source project to use Android tablets as extended displays for Linux over
USB, targeting up to 144 Hz. MIT licensed.

**Current status: phase 1 video transport prototype.** A Linux server sends a
moving H.264 test pattern to a native Android app through ADB reverse. It does
not create a second desktop monitor or capture the desktop yet. NVENC and
144 FPS end-to-end operation are future milestones, not validated features.

## Quick start — Ubuntu + Android

See [the Portuguese setup guide](docs/setup-pt.md) for detailed instructions and
troubleshooting. No GNOME upgrade is needed for this prototype.

Install Linux dependencies (Ubuntu 24.04):

```bash
sudo apt update
sudo apt install adb usbutils python3-gi gir1.2-gstreamer-1.0 \
  gir1.2-gst-plugins-base-1.0 gstreamer1.0-tools \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly
./scripts/doctor.sh
```

Build `android/` using Android Studio, or use JDK 17, Android SDK Platform 35 and
the included Gradle 8.9 wrapper:

```bash
cd android
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
cd ..
```

Enable USB debugging, connect a data-capable USB cable, accept the computer's
authorization on the tablet, then:

```bash
adb devices
./scripts/usb-connect.sh
./scripts/server.sh
```

Open **OpenPadDisplay** on the tablet. A moving ball should appear with diagnostic
FPS and panel refresh information. The app connects automatically and retries
if the server or USB connection disappears. Re-run `usb-connect.sh` after
unplugging the cable. Stop the server with Ctrl+C.

Default: **1920×1280, requested 60 FPS, 12 Mbit/s, software H.264**.
For an initial low-load check:

```bash
./scripts/server.sh --width 960 --height 640 --fps 30 --bitrate 4000
```

For an experimental 144 FPS source:

```bash
./scripts/server.sh --width 1920 --height 1280 --fps 144 --bitrate 24000
```

CPU encoding and tablet capabilities may limit these modes. Android chooses the
actual panel rate in response to the app's request. Panel refresh, source request
and distinct presented frames are separate measurements.

## Development

```text
android/    Kotlin + MediaCodec + SurfaceView client
linux/      Python + GStreamer test-pattern server and tests
protocol/   Versioned TCP framing specification
docs/       Setup, architecture and roadmap
scripts/    Diagnostics, USB mapping and server launcher
```

```bash
PYTHONPATH=linux /usr/bin/python3 -m unittest discover -s linux/tests -v
./scripts/server.sh --dry-run
```

Protocol tests use Python's standard library. The encoding integration test needs
GStreamer and x264 and is skipped with an explicit reason if unavailable. The
server binds only to loopback and needs neither root nor Internet while streaming.
Android's `INTERNET` permission permits the local TCP socket; Wi-Fi is not needed.

Read [the protocol](protocol/README.md) and [architecture and roadmap](docs/architecture.md)
before adding a virtual monitor backend or changing framing.
