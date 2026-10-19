# Architecture and roadmap

## Implemented: NVENC extended desktop prototype (0.3)

```text
Ubuntu / Python + GStreamer
  test-pattern: videotestsrc ────────────────────────────────┐
  virtual: Mutter RecordVirtual → PipeWire → videoconvert ──┤
    → videorate (drop only) → H.264 encoder (no B-frames) → appsink
    → framed TCP on 127.0.0.1:27183
      → adb reverse over USB
        → Kotlin / MediaCodec → SurfaceView
```

The server has explicit `--source test-pattern` and `--source virtual` modes.
The latter creates an additional output using Mutter's private ScreenCast API,
with an embedded pointer and `is-platform=true`. A private D-Bus owner and a
dedicated GLib context keep the session alive and dispatch the PipeWire node
signal. PipeWire negotiation creates the actual monitor at the requested size
and refresh rate. The server stops the pipeline before stopping the Mutter
session; disconnecting the bus owner is a second cleanup mechanism. Mutter may
remove the output shortly after the Stop reply. Saved display settings are not
edited. The output exists only while a client is connected.

Android retries after disconnection, rebuilds its decoder each session,
preserves aspect ratio, stops when backgrounded, and requests the stream refresh
rate through `Surface.setFrameRate()`. It labels the source using the existing
protocol's optional `source` metadata. Older APKs can still display the video.
Decoders
advertising the size/rate are considered; hardware decoders are preferred.
Unsupported modes produce an error asking for a lower mode.

The server reports encoded/sent FPS. Android logs received access units, frame
render callback FPS and the panel's reported refresh rate. Render callbacks are
diagnostic estimates, not proof that every frame was scanned out. The tablet displays
only the video in immersive full screen on `main`; `codex/debug` adds a diagnostic
overlay. Diagnostics also use the `OpenPadDisplay` logcat tag. There is no
end-to-end latency measurement or separate raw capture counter yet. The moving
ball helps reveal stalls but is not a frame-identity benchmark.

Virtual capture is variable-rate: `framerate=0/1,max-framerate=N/1`. Mutter 46
uses the negotiated maximum rate to configure its virtual monitor. It does not
require the newer `modes` property for this resizable virtual-output path.
Local tests confirmed a 960×640 output at both 60 Hz and 144 Hz, and 1920×1280
at 60 Hz. These are monitor-mode checks, not measurements of distinct presented
frames. PipeWire repeats the last buffer every second on an idle desktop to
keep the TCP/decoder session alive. Raw `videorate` drops excess frames without
creating a constant stream of duplicated frames. Encoded dependent frames are
never selectively dropped.

Opt-in integration tests create and capture real outputs, check the compositor's
active size/rate, and verify removal after both normal and exceptional exits.
They preserve existing outputs and are skipped by ordinary CI tests.

## Encoder selection and measurements

`--encoder auto` tries `nvh264enc` plus `h264parse`, then `x264enc` if hardware
startup fails before a header or frame is sent. Explicit `nvenc` never silently
uses the CPU. Midstream errors end the session; every reconnect gets fresh
headers and an IDR. NVENC accepts BGRA input for virtual capture (avoiding CPU
RGB-to-YUV conversion), while the test generator emits NV12 directly. It uses
CBR, no B-frames/lookahead, zero reordering
delay, and a fast low-latency preset supported by the installed plugin. The
parser repeats SPS/PPS at IDRs. x264 keeps its baseline/zerolatency settings.
A two-buffer raw queue overlaps generation/capture with encoding. It discards
old raw frames under load; encoded reference frames are never selectively dropped.

The Ubuntu dependency installer includes the official Bad Plugins package for
NVENC and parsing. Runtime GPU/driver failure can still trigger startup fallback.
The host reports separate capture-buffer and encoded/sent counts per interval,
video bitrate and CPU usage. Raw capture counts include idle repeats and do not
assert unique desktop content. The optional benchmark uses an animated source
with warmup and reports host-only throughput; USB and Android are excluded.
Hardware integration tests verify stream headers and decode using the real GPU;
fallback tests run on CPU-only CI hosts. An inexpensive scrolling-bars source
is available for high-FPS benchmarks, since the ball generator can be the limit.
Android requests a matching native display mode and allows rate changes on
API 31+, while still reporting the actual panel rate chosen by the OS.

## Next milestones

1. **144 FPS validation:** verify compositor, capture, encoder, USB throughput,
   decoder and presentation independently. Test lower resolutions first, then
   1920×1280, 2560×1708 and 3200×2136. These are targets, not guarantees.
2. **Input and usability:** touch/stylus return channel, rotation, capability
   negotiation, start/stop controls and host mode selection.
3. **Distribution:** investigate non-ADB transports, installation and packaging.

No GNOME upgrade is required for the tested Mutter 46 backend. Support on other
compositors and Mutter versions needs separate testing because this is a private
API. Requesting a 144 Hz virtual monitor does not guarantee 144 FPS through the
encoder, USB connection, decoder and tablet panel.

## Technical references

- [ADB](https://developer.android.com/tools/adb)
- [MediaCodec](https://developer.android.com/reference/android/media/MediaCodec)
- [Surface.setFrameRate](https://developer.android.com/reference/android/view/Surface#setFrameRate(float,int))
- [GStreamer x264enc](https://gstreamer.freedesktop.org/documentation/x264/index.html)
- [GStreamer appsink](https://gstreamer.freedesktop.org/documentation/app/appsink.html)
- [Mutter 46 ScreenCast interface](https://github.com/GNOME/mutter/blob/gnome-46/data/dbus-interfaces/org.gnome.Mutter.ScreenCast.xml)
- [Mutter 46 virtual-monitor negotiation](https://github.com/GNOME/mutter/blob/gnome-46/src/backends/meta-screen-cast-virtual-stream-src.c)
- [PipeWire 1.0.5 GStreamer format mapping](https://github.com/PipeWire/pipewire/blob/1.0.5/src/gst/gstpipewireformat.c)
- [AGP 8.7 compatibility](https://developer.android.com/build/releases/agp-8-7-0-release-notes)
