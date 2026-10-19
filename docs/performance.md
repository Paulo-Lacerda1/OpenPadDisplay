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
