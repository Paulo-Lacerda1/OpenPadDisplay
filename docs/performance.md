# Performance validation — 2026-10-19

Local measurements on Ubuntu, GNOME/Mutter 46, GStreamer 1.24.2 and an NVIDIA
RTX 3050 Ti Laptop GPU (driver 580.178.04), connected by USB to a Xiaomi Pad 8 Pro.
These are development measurements on one machine, not guaranteed performance.

## Host encoder comparison

1920×1280, requested 144 FPS, H.264 at 24 Mbit/s, scrolling color bars, 2 seconds
of warmup followed by 8 seconds of measurement. Runs were sequential. CPU is
process time relative to one logical core; 100% means one core fully occupied.

| Encoder | Encoded FPS | Process CPU | Video bitrate |
| --- | ---: | ---: | ---: |
| NVENC | 144.00 | 56.7% | 24.60 Mbit/s |
| x264 ultrafast | 144.01 | 287.6% | 24.28 Mbit/s |

```bash
./scripts/server.sh --encoder nvenc --pattern scroll --fps 144 --bitrate 24000 --benchmark 8
./scripts/server.sh --encoder x264 --pattern scroll --fps 144 --bitrate 24000 --benchmark 8
```

This benchmark excludes USB, Android decoding and panel presentation. The ball
generator can itself limit throughput, so use the scrolling pattern to compare
encoders. NVENC receives NV12 for generated patterns and BGRA for virtual capture
to avoid a CPU color conversion in the desktop path.

## USB and tablet

With the scrolling pattern, the host encoded/sent approximately 144 FPS and the
Android app reported approximately 144 received FPS and rendering callbacks per
second. The panel reported 144 Hz after its previous 120 Hz refresh cap was
raised. Rendering callbacks and panel frequency do not establish that every
physical scanout contained a distinct frame. End-to-end latency was not measured.

## Real extended desktop

The GNOME virtual monitor successfully negotiated 1920×1280 at 144 Hz. During
continuous desktop animation, one-second Android readings varied approximately
108–135 FPS. Host capture and encoding rates tracked each other, generally around
110–130 FPS, placing the remaining throughput limit upstream of encoding in the
Mutter/PipeWire capture path. This does not yet establish a specific root cause.

The desktop therefore does **not yet sustain 144 distinct presented FPS**. Idle
desktop traffic falls to roughly one keepalive frame per second, which is expected.
Future performance work should investigate capture scheduling and copying, then
validate frame identity and latency across the complete path.

## Pipeline overhead improvements

The `perf/pipeline-and-decoder-overhead` branch moves raw frame rate limiting
before color conversion. In a controlled 144-to-60 FPS test, 144 source buffers
previously entered `videoconvert` to produce 60 encoded frames; now only 60 enter
the converter for the same 60 encoded frames. This removes 58.3% of converter
invocations in that case. It is not a claim of 58.3% lower total CPU or higher
desktop FPS; when the source already meets its requested cadence, there may be
no excess frames to discard.

Host capture counting now polls native `identity.stats` once per report instead
of calling Python for every raw frame, and disables unused identity handoff
signals. GStreamer's [identity documentation](https://gstreamer.freedesktop.org/documentation/coreelements/identity.html)
describes these counters (available since 1.20). Android's frame rendered
callbacks now run on a dedicated session thread rather than the main UI thread.
These changes remove work from the capture and UI paths; they do not establish
an increase in distinct physical scanouts.

Host interval reports also include:

- `rate_dropped`: raw frames discarded by `videorate` during the interval.
- `raw_queue`: raw buffers waiting when the report is taken, bounded at two.
- `send_max_ms`: longest complete frame serialization/socket write in the
  interval. This excludes capture, encoding, decoder and panel time, and can
  include operating system scheduling delays. It is not end-to-end latency.

Encoded dependent H.264 frames are still never selectively dropped. PipeWire
`always-copy=true` is retained: avoiding that large raw copy needs a separate
buffer lifetime and capture benchmark before changing the default.

Validation after these changes:

- All 13 Linux tests passed with both GPU and virtual display integration
  enabled. The new BGRA-to-I420 rate limiting test rejects the old ordering
  (144 converter inputs for 60 outputs) and passes the new ordering (60/60).
- A 16-second USB scrolling-pattern run at 1920×1280, 144 FPS and 24 Mbit/s
  sustained 144.0 host FPS after startup. Android reported 143.7–144.3 received
  FPS and rendered callbacks, with a 144 Hz panel. Host intervals reported
  58.3–63.5% process CPU, no rate drops, zero sampled raw queue occupancy, and
  0.19–0.28 ms maximum frame write time. These are current-run measurements,
  not an isolated before/after CPU comparison or proof of distinct scanouts.
- The Android APK was rebuilt and installed. The original ADB mapping and
  extended desktop session were restored after the scrolling-pattern test.
