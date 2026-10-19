# Architecture and roadmap

## Implemented: phase 1

```text
Ubuntu / Python + GStreamer
  videotestsrc → x264enc (CPU, no B-frames) → appsink (access units)
    → framed TCP on 127.0.0.1:27183
      → adb reverse over USB
        → Kotlin / MediaCodec → SurfaceView
```

The prototype validates video transport without desktop capture permissions or
display configuration changes. Android retries after disconnection, rebuilds its
decoder each session, preserves aspect ratio, stops when backgrounded, and
requests the stream refresh rate through `Surface.setFrameRate()`. Decoders
advertising the size/rate are considered; hardware decoders are preferred.
Unsupported modes produce an error asking for a lower mode.

The server reports encoded/sent FPS. Android reports received access units, frame
render callback FPS and the panel's reported refresh rate. Render callbacks are
diagnostic estimates, not proof that every frame was scanned out. There is no
end-to-end latency measurement yet. Captured FPS requires a capture backend.
The moving ball helps reveal stalls but is not a frame-identity benchmark.

## Next milestones

1. **Extended desktop:** investigate `org.gnome.Mutter.ScreenCast`, `RecordVirtual`,
   PipeWire node negotiation and monitor lifecycle on the actual Ubuntu/GNOME
   version. Release sessions on shutdown/disconnect. Introduce a source/backend
   interface when adding the second source.
2. **Hardware encoding:** probe NVENC and driver compatibility; add an explicit
   encoder option and software fallback with truthful metrics.
3. **144 FPS validation:** verify compositor, capture, encoder, USB throughput,
   decoder and presentation independently. Test lower resolutions first, then
   1920×1280, 2560×1708 and 3200×2136. These are targets, not guarantees.
4. **Input and usability:** touch/stylus return channel, rotation, capability
   negotiation, start/stop controls and host mode selection.
5. **Distribution:** investigate non-ADB transports, installation and packaging.

Do not upgrade GNOME as a prerequisite for phase 1. `--fps 144` does not make
GNOME 46 create a 144 Hz virtual monitor. Mutter's private APIs and virtual
refresh configuration require version-specific testing.

## Technical references

- [ADB](https://developer.android.com/tools/adb)
- [MediaCodec](https://developer.android.com/reference/android/media/MediaCodec)
- [Surface.setFrameRate](https://developer.android.com/reference/android/view/Surface#setFrameRate(float,int))
- [GStreamer x264enc](https://gstreamer.freedesktop.org/documentation/x264/index.html)
- [GStreamer appsink](https://gstreamer.freedesktop.org/documentation/app/appsink.html)
- [Mutter ScreenCast interface source](https://gitlab.gnome.org/GNOME/mutter/-/blob/main/data/dbus-interfaces/org.gnome.Mutter.ScreenCast.xml)
- [AGP 8.7 compatibility](https://developer.android.com/build/releases/agp-8-7-0-release-notes)
