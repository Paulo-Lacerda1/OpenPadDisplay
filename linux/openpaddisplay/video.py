"""H.264 streaming from a live test pattern or a Mutter virtual output."""

import time
import sys

from .protocol import write_frame, write_header, write_telemetry


class EncoderStartupError(RuntimeError):
    """The encoder failed before publishing a session header or any video."""


def encoder_candidates(Gst, requested):
    available = {
        "nvenc": all(Gst.ElementFactory.find(name) for name in ("nvh264enc", "h264parse")),
        "x264": Gst.ElementFactory.find("x264enc") is not None,
    }
    if requested != "auto":
        if not available[requested]:
            raise RuntimeError(f"Encoder {requested} unavailable; run scripts/install-deps.sh and scripts/doctor.sh")
        return [requested]
    candidates = [name for name in ("nvenc", "x264") if available[name]]
    if not candidates:
        raise RuntimeError("No H.264 encoder available; run scripts/install-deps.sh")
    return candidates


def nvenc_preset(Gst):
    # GStreamer 1.24 uses legacy names; newer versions expose P1–P7 and tune.
    element = Gst.ElementFactory.make("nvh264enc")
    if element is None:
        raise EncoderStartupError("Could not create nvh264enc")
    presets = {v.value_nick for v in type(element.get_property("preset")).__enum_values__.values()}
    if "p1" in presets:
        result = "preset=p1"
        if element.find_property("tune"):
            tunes = {v.value_nick for v in type(element.get_property("tune")).__enum_values__.values()}
            if "ultra-low-latency" in tunes:
                result += " tune=ultra-low-latency"
        return result
    return "preset=low-latency-hp" if "low-latency-hp" in presets else ""


def pipeline_description(width, height, fps, bitrate, node_id=None, encoder="x264",
                         nvenc_options="preset=low-latency-hp", pattern="ball"):
    if node_id is None:
        test_pattern = "pattern=smpte horizontal-speed=4" if pattern == "scroll" else "pattern=ball"
        source = (f"videotestsrc is-live=true {test_pattern} ! "
                  f"video/x-raw,width={width},height={height},framerate={fps}/1 ! ")
    else:
        source = (
            f"pipewiresrc path={int(node_id)} do-timestamp=true always-copy=true keepalive-time=1000 ! "
            f"video/x-raw,width={width},height={height},framerate=0/1,max-framerate={fps}/1 ! "
        )
    if encoder == "nvenc":
        # Preserve captured RGB for GPU conversion; the test generator can emit NV12 directly.
        pixel_format = "BGRA" if node_id is not None else "NV12"
        encode = (
            f"nvh264enc name=encoder {nvenc_options} zerolatency=true bframes=0 rc-lookahead=0 "
            f"rc-mode=cbr bitrate={bitrate} gop-size={fps} ! "
            "video/x-h264,stream-format=byte-stream,alignment=au,profile=baseline ! "
            "h264parse config-interval=-1 ! "
        )
    elif encoder == "x264":
        pixel_format = "I420"
        encode = (
            f"x264enc name=encoder tune=zerolatency speed-preset=ultrafast bitrate={bitrate} "
            f"key-int-max={fps} bframes=0 byte-stream=true option-string=repeat-headers=1 ! "
        )
    else:
        raise ValueError(f"Unknown encoder: {encoder}")
    return (
        source + "identity name=capture silent=true signal-handoffs=false ! "
        "queue name=raw_queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 leaky=downstream ! "
        # Discard excess raw frames before spending CPU on color conversion.
        f"videorate name=rate drop-only=true skip-to-first=true ! video/x-raw,framerate={fps}/1 ! "
        f"videoconvert ! video/x-raw,format={pixel_format} ! "
        + encode +
        "video/x-h264,stream-format=byte-stream,alignment=au,profile=baseline ! "
        "appsink name=video sync=false max-buffers=2 drop=false"
    )


def load_gst(virtual=False, encoder="x264"):
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
    except (ImportError, ValueError) as exc:
        raise RuntimeError("Install python3-gi and gir1.2-gstreamer-1.0; use /usr/bin/python3") from exc
    Gst.init(None)
    elements = ("videoconvert", "videorate", "identity", "queue", "appsink", "pipewiresrc" if virtual else "videotestsrc")
    for name in elements:
        if Gst.ElementFactory.find(name) is None:
            raise RuntimeError(f"Missing GStreamer element: {name}. Run scripts/doctor.sh")
    encoder_candidates(Gst, encoder)
    return Gst


def stream_video(connection, args, monitor=None, send_header=False):
    requested = getattr(args, "encoder", "x264")
    Gst = load_gst(virtual=monitor is not None, encoder=requested)
    candidates = encoder_candidates(Gst, requested)
    for index, encoder in enumerate(candidates):
        try:
            return _stream_pipeline(Gst, connection, args, monitor, encoder, send_header)
        except EncoderStartupError as exc:
            if index + 1 == len(candidates):
                raise
            print(f"{encoder} startup failed: {exc}; retrying with {candidates[index + 1]}",
                  file=sys.stderr, flush=True)


def _stream_pipeline(Gst, connection, args, monitor, encoder, send_header):
    from gi.repository import GLib
    try:
        pipeline = Gst.parse_launch(pipeline_description(
            args.width, args.height, args.fps, args.bitrate,
            node_id=monitor.node_id if monitor else None,
            encoder=encoder, nvenc_options=nvenc_preset(Gst) if encoder == "nvenc" else "",
            pattern=getattr(args, "pattern", "ball"),
        ))
    except GLib.Error as exc:
        raise EncoderStartupError(f"Could not construct the video pipeline: {exc.message}") from exc
    sink = pipeline.get_by_name("video")
    bus = pipeline.get_bus()
    frames = 0
    # Poll native counters when reporting instead of taking the GIL on every frame.
    capture = pipeline.get_by_name("capture")
    rate = pipeline.get_by_name("rate")
    raw_queue = pipeline.get_by_name("raw_queue")
    last_report = last_sample = time.monotonic()
    last_cpu = time.process_time()
    last_frames = last_captured = last_rate_dropped = sent_bytes = 0
    max_send_seconds = 0
    diagnostics = getattr(args, "diagnostics", False)
    telemetry_sequence = 0
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Could not start GStreamer pipeline")
        while True:
            if monitor and monitor.closed.is_set():
                raise RuntimeError("GNOME closed the virtual monitor session")
            sample = sink.emit("try-pull-sample", Gst.SECOND)
            if sample is None:
                message = bus.timed_pop_filtered(0, Gst.MessageType.ERROR | Gst.MessageType.EOS)
                if message:
                    if message.type == Gst.MessageType.ERROR:
                        error, detail = message.parse_error()
                        raise RuntimeError(f"GStreamer: {error.message} ({detail})")
                    return
                # A stalled encoder must not hold this session indefinitely.
                timeout = 3 if frames == 0 else 10
                if time.monotonic() - last_sample > timeout:
                    raise RuntimeError(f"No video produced for {timeout} seconds")
                continue
            buffer = sample.get_buffer()
            if buffer.pts == Gst.CLOCK_TIME_NONE:
                raise RuntimeError("Encoder returned a frame without PTS")
            payload = buffer.extract_dup(0, buffer.get_size())
            if frames == 0:
                # The output only exists once PipeWire has negotiated and
                # produced video. Position it once before publishing a session.
                if monitor and getattr(args, "position", None) is not None:
                    monitor.apply_position()
                print(f"Streaming with {encoder} ({pipeline.get_by_name('encoder').get_factory().get_name()})", flush=True)
                if send_header:
                    write_header(connection, args.width, args.height, args.fps,
                                 source=args.source, encoder=encoder, diagnostics=diagnostics)
            send_started = time.monotonic()
            write_frame(connection, payload, buffer.pts // 1000, diagnostics=diagnostics)
            frames += 1
            sent_bytes += len(payload)
            now = time.monotonic()
            max_send_seconds = max(max_send_seconds, now - send_started)
            last_sample = now
            if now - last_report >= 2:
                elapsed = now - last_report
                cpu = time.process_time()
                count = capture.get_property("stats").get_value("num-buffers")
                rate_dropped = rate.get_property("drop")
                if diagnostics:
                    telemetry_sequence += 1
                    write_telemetry(connection, {
                        "sequence": telemetry_sequence,
                        "interval_seconds": elapsed,
                        "capture_fps": (count - last_captured) / elapsed,
                        "encoded_fps": (frames - last_frames) / elapsed,
                        "rate_dropped": rate_dropped - last_rate_dropped,
                        "raw_queue": raw_queue.get_property("current-level-buffers"),
                        "send_max_ms": max_send_seconds * 1000,
                        "bitrate_mbps": sent_bytes * 8 / elapsed / 1e6,
                        "cpu_percent": (cpu - last_cpu) * 100 / elapsed,
                    }, buffer.pts // 1000)
                print(f"encoder={encoder} capture_buffers={(count - last_captured) / elapsed:.1f} "
                      f"encoded/sent={(frames - last_frames) / elapsed:.1f} FPS "
                      f"rate_dropped={rate_dropped - last_rate_dropped} "
                      f"raw_queue={raw_queue.get_property('current-level-buffers')} "
                      f"send_max_ms={max_send_seconds * 1000:.2f} "
                      f"bitrate={sent_bytes * 8 / elapsed / 1e6:.2f} Mbit/s "
                      f"cpu={(cpu - last_cpu) * 100 / elapsed:.1f}%", flush=True)
                last_report = now
                last_cpu, last_frames, last_captured, sent_bytes = cpu, frames, count, 0
                last_rate_dropped, max_send_seconds = rate_dropped, 0
    except RuntimeError as exc:
        if frames == 0:
            raise EncoderStartupError(str(exc)) from exc
        raise
    finally:
        if monitor and getattr(args, "position", None) is not None:
            monitor.prepare_cleanup()
        pipeline.set_state(Gst.State.NULL)
