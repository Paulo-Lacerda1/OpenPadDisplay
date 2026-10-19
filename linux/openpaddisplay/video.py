"""Live test-pattern source. The virtual desktop backend is a future milestone."""

import time

from .protocol import write_frame


def pipeline_description(width, height, fps, bitrate):
    return (
        "videotestsrc is-live=true pattern=ball ! "
        f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
        "videoconvert ! video/x-raw,format=I420 ! "
        f"x264enc tune=zerolatency speed-preset=ultrafast bitrate={bitrate} "
        f"key-int-max={fps} bframes=0 byte-stream=true "
        "option-string=repeat-headers=1 ! "
        "video/x-h264,stream-format=byte-stream,alignment=au,profile=baseline ! "
        "appsink name=video sync=false max-buffers=2 drop=false"
    )


def load_gst():
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
    except (ImportError, ValueError) as exc:
        raise RuntimeError("Install python3-gi and gir1.2-gstreamer-1.0; use /usr/bin/python3") from exc
    Gst.init(None)
    for name in ("videotestsrc", "videoconvert", "x264enc", "appsink"):
        if Gst.ElementFactory.find(name) is None:
            raise RuntimeError(f"Missing GStreamer element: {name}. Run scripts/doctor.sh")
    return Gst


def stream_video(connection, args):
    Gst = load_gst()
    pipeline = Gst.parse_launch(pipeline_description(args.width, args.height, args.fps, args.bitrate))
    sink = pipeline.get_by_name("video")
    bus = pipeline.get_bus()
    frames = 0
    started = time.monotonic()
    last_report = started
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Could not start GStreamer pipeline")
        while True:
            sample = sink.emit("try-pull-sample", Gst.SECOND)
            if sample is None:
                message = bus.timed_pop_filtered(0, Gst.MessageType.ERROR | Gst.MessageType.EOS)
                if message:
                    if message.type == Gst.MessageType.ERROR:
                        error, detail = message.parse_error()
                        raise RuntimeError(f"GStreamer: {error.message} ({detail})")
                    return
                # A stalled encoder must not hold this session indefinitely.
                if time.monotonic() - last_report > 10:
                    raise RuntimeError("No video produced for 10 seconds")
                continue
            buffer = sample.get_buffer()
            if buffer.pts == Gst.CLOCK_TIME_NONE:
                raise RuntimeError("Encoder returned a frame without PTS")
            payload = buffer.extract_dup(0, buffer.get_size())
            write_frame(connection, payload, buffer.pts // 1000)
            frames += 1
            now = time.monotonic()
            if now - last_report >= 2:
                print(f"Encoded/sent: {frames / (now - started):.1f} FPS (session average)", flush=True)
                last_report = now
    finally:
        pipeline.set_state(Gst.State.NULL)
