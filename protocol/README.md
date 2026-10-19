# OpenPadDisplay wire protocol v1

The Linux host listens on **127.0.0.1:27183**. `adb reverse tcp:27183 tcp:27183`
maps the Android loopback port to the host. The Android app is the TCP client.
No Wi-Fi connection, network discovery, or public listener is required. Both
ends use plain TCP, intended for a trusted local ADB connection.

All integers are unsigned, big-endian. Android reads into signed types and rejects
negative values. Read exactly the specified bytes: TCP reads are not messages.

## Session header (host → tablet)

| Field | Size | Value |
|---|---|---|
| Magic/version | 8 bytes | ASCII `OPAD0001` |
| Metadata length | u32 | 1–4096 bytes |
| Metadata | length bytes | UTF-8 JSON |

```json
{"codec":"h264","width":1920,"height":1280,"fps":60,"source":"test-pattern"}
```

Dimensions must be even and in 2–4096; FPS in 1–144. FPS describes the requested
source cadence, not a measured result or capability negotiation. Unknown JSON
fields may be ignored. Other codecs/versions must be rejected.

`source` is `test-pattern` or `virtual`. It describes whether pixels come from
the diagnostic source or from a real Mutter virtual monitor. Older clients can
ignore it and still decode the same H.264 records. New clients default to
`test-pattern` when the field is omitted and display a generic label for unknown
sources. No wire version change is required.

## Repeating video record (host → tablet)

| Field | Size | Value |
|---|---|---|
| Payload length | u32 | 1–8,388,608 bytes |
| Presentation timestamp | u64 | microseconds in the encoder timeline |
| Payload | length bytes | one complete H.264 Annex-B access unit |

The first access unit includes SPS, PPS and IDR; Android extracts SPS/PPS as
`csd-0`/`csd-1` before decoder configuration. There are no B-frames. Timestamps
increase; their origin is arbitrary and cannot be compared to the tablet clock
to infer latency. Mode changes require a new connection and decoder. EOF or a
malformed record ends the session; there is no separate end marker.

Every connection starts a new encoder and header so a reconnect has no dependency
on old frames. Backpressure is bounded by appsink and socket send timeouts.
Encoded dependent frames are not selectively dropped. Capability negotiation,
input events and telemetry sent to the host are future extensions.

For `virtual`, PipeWire negotiates a variable-rate capture stream using
`framerate=0/1` and `max-framerate=<requested>/1`. An idle desktop can send far
fewer frames than requested. The host keeps idle connections alive with periodic
copies of the last captured frame; these are not distinct captured images.
