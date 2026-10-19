# OpenPadDisplay

An open-source project to use Android tablets as extended displays for Linux over
USB, targeting up to 144 Hz. MIT licensed.

**Current status: extended desktop prototype for GNOME Wayland.** The Linux
server can create a real virtual monitor with Mutter, capture it through
PipeWire, and send H.264 video to Android through ADB reverse. A moving test
pattern remains available for diagnostics. Encoding automatically prefers NVIDIA
NVENC, with a CPU fallback at startup. The app reports the actual host encoder.
144 distinct presented frames per second remain a performance target to validate.

## Quick start — Ubuntu + Android

See [the Portuguese setup guide](docs/setup-pt.md) for detailed instructions and
troubleshooting. No GNOME upgrade is needed for this prototype.

Install Linux dependencies (Ubuntu 24.04):

```bash
./scripts/install-deps.sh
./scripts/doctor.sh
```

The installer includes `gstreamer1.0-plugins-bad`, which provides `nvh264enc`
and `h264parse`. A working NVIDIA driver is required for hardware encoding.
Preview package commands with `./scripts/install-deps.sh --dry-run`.

The dependency installer also adds **OpenPadDisplay** to your Ubuntu application
menu when run as your desktop user. If dependencies are already installed, run
`./scripts/install-desktop.py` without sudo. Open the app, connect the tablet by
USB, choose a refresh rate and click **Ligar tablet**. **Desligar tablet**, or
closing the window, stops its stream and removes its virtual monitor. The launcher
uses the installed Android app; install the APK first as described below. Keep
this checkout at its current location, or rerun the launcher installer after moving it.

The same [shared icon](assets/branding/openpaddisplay.png) is used on Linux and
Android. Artwork provenance and regeneration are in [branding](assets/branding/README.md).

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

Open **OpenPadDisplay** on the tablet. A moving ball should appear in full screen
with a diagnostic overlay on this `debug` branch.
Diagnostics are available with `adb logcat -s OpenPadDisplay:I`. The app connects
automatically and retries
if the server or USB connection disappears. Re-run `usb-connect.sh` after
unplugging the cable. Stop the server with Ctrl+C.

Default: **1920×1280, requested 60 FPS, 12 Mbit/s, automatic H.264 encoder**.
For an initial low-load check:

```bash
./scripts/server.sh --width 960 --height 640 --fps 30 --bitrate 4000
```

For an experimental 144 FPS source:

```bash
./scripts/server.sh --width 1920 --height 1280 --fps 144 --bitrate 24000
```

Capture, encoding and tablet capabilities may limit these modes. Android chooses the
actual panel rate in response to the app's request. Panel refresh, source request
and distinct presented frames are separate measurements.

## Extended desktop

After installing the APK and authorizing USB debugging, run from a GNOME Wayland
desktop terminal:

```bash
./scripts/extend-usb.sh
```

This opens the installed app, maps the USB connection and starts a **1920×1280,
requested 60 Hz** virtual display. GNOME adds an output such as `Meta-0`; use
Settings → Displays to inspect its position. In the tested configuration it is
placed to the right of the laptop, so drag a window across the right edge to
see it on the tablet. Stop the host with Ctrl+C. The virtual output is removed
when the client disconnects or the server stops; GNOME moves its windows back
to the remaining displays. Reconnecting creates a new output.

For a lighter mode:

```bash
./scripts/extend-usb.sh --width 960 --height 640 --fps 60 --bitrate 4000
```

Mutter 46 was verified locally to negotiate 960×640 at 60 Hz and at 144 Hz via
PipeWire's `max-framerate`. A GNOME upgrade is not required for this backend.
An idle desktop produces fewer frames; a keepalive prevents decoder/network
timeouts. FPS while idle is not a performance benchmark. Touch/stylus control
is a future extension; use the PC's keyboard and mouse.

## Encoding and performance

`--encoder auto` (default) tries NVENC first and falls back to x264 if startup
fails before any session header or video is sent. `--encoder nvenc` requires
hardware encoding and reports errors; `--encoder x264` forces the CPU. An error
after streaming starts ends that session rather than changing its bitstream.

```bash
./scripts/extend-usb.sh --encoder nvenc --fps 144 --bitrate 24000
```

Host logs show capture buffers, encoded/sent FPS, video bitrate and process CPU
usage over each reporting interval. Capture buffers include idle keepalive copies.
Android logs received FPS, rendered callbacks, host encoder, decoder and panel
refresh rate. Callbacks do not prove distinct scanouts or end-to-end latency.

The `main` branch displays only the video. The `debug` branch also displays
these diagnostics as an overlay on the tablet. Build and install the APK from the
branch matching the desired behavior.

Run a repeatable **host-only** benchmark with an animated test source, a 2-second
warmup, and an 8-second measurement window:

```bash
./scripts/server.sh --encoder nvenc --pattern scroll --fps 144 --bitrate 24000 --benchmark 8
./scripts/server.sh --encoder x264 --pattern scroll --fps 144 --bitrate 24000 --benchmark 8
```

Run these sequentially for a useful CPU comparison. `BENCHMARK` prints a JSON
summary with the actual encoder. It excludes USB, Android decoding and panel
presentation. CPU percentage is relative to one logical core and can exceed 100%.
Benchmarking an idle `--source virtual` measures idle updates, not maximum capacity.
The default ball generator can itself limit throughput at high resolutions.
`--pattern scroll` generates inexpensive moving color bars for performance tests.

See [local performance results](docs/performance.md) for the encoder comparison,
USB validation and remaining real-desktop capture limit.

## Development

```text
android/    Kotlin + MediaCodec + SurfaceView client
linux/      Python, Mutter/PipeWire capture, GStreamer encoder and tests
protocol/   Versioned TCP framing specification
docs/       Setup, architecture and roadmap
scripts/    Diagnostics, USB mapping and server launcher
```

```bash
PYTHONPATH=linux /usr/bin/python3 -m unittest discover -s linux/tests -v
./scripts/server.sh --dry-run
```

Opt-in desktop integration tests briefly create real monitors and check capture,
refresh negotiation and cleanup, including failure recovery:

```bash
OPENPADDISPLAY_TEST_VIRTUAL=1 PYTHONPATH=linux /usr/bin/python3 -m unittest discover -s linux/tests -v
```

On an NVIDIA host, also set `OPENPADDISPLAY_TEST_NVENC=1` to test real hardware
headers, framing and decoding. Ordinary CI tests exercise fallback without a GPU.

Protocol tests use Python's standard library. The encoding integration test needs
GStreamer and x264 and is skipped with an explicit reason if unavailable. The
server binds only to loopback and needs neither root nor Internet while streaming.
Android's `INTERNET` permission permits the local TCP socket; Wi-Fi is not needed.

Read [the protocol](protocol/README.md) and [architecture and roadmap](docs/architecture.md)
before adding a virtual monitor backend or changing framing.
