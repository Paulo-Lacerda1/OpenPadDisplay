# OpenPadDisplay wire protocol v1 and opt-in v2

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

An optional `encoder` field identifies the actual host encoder (`nvenc` or
`x264`). The host publishes metadata only after the chosen encoder has produced
its first valid access unit. Automatic startup fallback therefore cannot publish
an incorrect encoder label or send two headers on one connection. A failure
after streaming begins ends the session instead of switching bitstreams.

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

## Optional v2: live host diagnostics

The host defaults to v1. `--diagnostics` explicitly selects v2 and requires the
Android 0.4+ app; the new app also accepts v1 hosts. Old clients reject the new
magic immediately. Telemetry is never inserted into a v1 H.264 stream.

The session header retains the same length and JSON framing, with magic
**`OPAD0002`**. It reports the actual encoder after the first encoded access unit
exists. The first record is video containing codec configuration and an IDR.

Subsequent records use the following header:

| Field | Size | Meaning |
| --- | --- | --- |
| Type | u8 | 1 = H.264 access unit, 2 = host telemetry JSON, 3 = timed-test completion JSON |
| Payload length | u32 | Type 1: 1–8,388,608; types 2/3: 1–4096 bytes |
| PTS | u64 | Most recent video presentation timestamp, microseconds |
| Payload | length bytes | Annex-B H.264 for type 1; UTF-8 JSON for types 2/3 |

Type 2 is emitted about every two seconds, after a video record. It contains:

```json
{"sequence":1,"interval_seconds":2.0,"capture_fps":144.0,"encoded_fps":144.0,"rate_dropped":0,"raw_queue":0,"send_max_ms":0.2,"bitrate_mbps":24.0,"cpu_percent":60.0}
```

`sequence` starts at 1, increases each interval, and resets on reconnect. Rates describe the
host measurement interval. `rate_dropped` counts raw cadence drops in that
interval; `raw_queue` is the sampled waiting queue level (0–2). These are not USB
packet losses. `send_max_ms` only measures video-record writes, including socket
backpressure. The timestamp has the video timeline's arbitrary origin and is
not a synchronized tablet clock or end-to-end latency measurement.

The client validates types, lengths and nonnegative finite metrics before use,
separates telemetry from decoder input, marks telemetry stale after five seconds,
and bounds consecutive metadata records to avoid starving video. The guided
test de-duplicates host sequence numbers before averaging host intervals or
adding cadence drops. Display/render callbacks remain informational.


## Timed RGB test (v2, Android 0.4.2+)

`--source test-pattern --pattern scroll --duration 10 --diagnostics` runs one
connection and exits after ten seconds from the first video record sent. The
launcher enables telemetry in all its sessions; the CLI still defaults to v1.
Timed sessions add `test_id` (a unique identifier per connection) and
`test_duration_seconds` (integer 1–3600) to the header. These fields must appear
together, with a v2 test-pattern source.

The Android client begins collecting automatically on this header, discarding
the initial two seconds of warmup. Normal EOF/reconnection without completion
cancels the collection; it must not present an interrupted test as completed.

After the final video record, the host sends type **3** with its most recent PTS:

```json
{"event":"test_complete","test_id":"unique-session-id","duration_seconds":10,"elapsed_seconds":10.002}
```

The identifier and duration must match the header and elapsed time must be finite
and at least the requested duration. This record finalizes the Android diagnosis
before the socket closes. Its result remains available through the ADB control
status while the launcher restores the normal virtual session. The host also
prints `TEST_RESULT` JSON with the same ID, duration, actual elapsed time, frame
count, encoder and mode; this is a host summary, not a measurement of distinct
physical frames. The launcher matches both results before showing a diagnosis.

The type-3 extension is only sent for timed diagnostic tests, which require APK
0.4.2+. Continuous v1/v2 streaming and older compatible clients are unchanged.
