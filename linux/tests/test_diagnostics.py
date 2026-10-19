import io
import json
import math
import socket
import threading
import unittest

from openpaddisplay.__main__ import parse_args
from openpaddisplay.protocol import (FRAME, LENGTH, MAGIC, MAGIC_DIAGNOSTICS,
                                    MAX_METADATA, RECORD, TELEMETRY_RECORD, VIDEO_RECORD,
                                    write_frame, write_header, write_telemetry)
from openpaddisplay.video import load_gst, stream_video
from test_protocol import exact


class Buffer:
    def __init__(self):
        self.data = bytearray()

    def sendall(self, value):
        self.data.extend(value)


class DiagnosticProtocolTests(unittest.TestCase):
    def test_default_keeps_v1_header_and_video_framing(self):
        stream = Buffer()
        write_header(stream, 1920, 1280, 144)
        self.assertEqual(stream.data[:8], MAGIC)
        stream = Buffer()
        write_frame(stream, b"\0\0\0\1\x65", 1234)
        self.assertEqual(stream.data, FRAME.pack(5, 1234) + b"\0\0\0\1\x65")

    def test_v2_types_keep_telemetry_out_of_h264_payload(self):
        stream = Buffer()
        write_header(stream, 960, 640, 60, diagnostics=True)
        self.assertEqual(stream.data[:8], MAGIC_DIAGNOSTICS)
        stream = Buffer()
        payload = b"\0\0\0\1\x65"
        write_frame(stream, payload, 100, diagnostics=True)
        fields = {"sequence": 1, "capture_fps": 60.0}
        write_telemetry(stream, fields, 100)
        reader = io.BytesIO(stream.data)
        self.assertEqual(RECORD.unpack(reader.read(RECORD.size)), (VIDEO_RECORD, len(payload), 100))
        self.assertEqual(reader.read(len(payload)), payload)
        kind, size, pts = RECORD.unpack(reader.read(RECORD.size))
        self.assertEqual((kind, pts), (TELEMETRY_RECORD, 100))
        self.assertEqual(json.loads(reader.read(size)), fields)

    def test_invalid_telemetry_does_not_write_partial_record(self):
        for value in ({"x": "a" * MAX_METADATA}, {"x": math.nan}, {"x": math.inf}):
            stream = Buffer()
            with self.assertRaises(ValueError):
                write_telemetry(stream, value, 0)
            self.assertFalse(stream.data)

    def test_live_metrics_are_opt_in_and_excluded_from_host_only_benchmark(self):
        self.assertFalse(parse_args([]).diagnostics)
        self.assertTrue(parse_args(["--diagnostics"]).diagnostics)
        import contextlib
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["--diagnostics", "--benchmark", "8"])

    def test_real_v2_video_then_telemetry_then_video_and_disconnect_cleanup(self):
        try:
            load_gst()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        args = parse_args(["--encoder", "x264", "--diagnostics", "--width", "320",
                           "--height", "240", "--fps", "30", "--pattern", "scroll"])
        sender, receiver = socket.socketpair()
        errors = []

        def produce():
            with sender:
                sender.settimeout(3)
                try:
                    stream_video(sender, args, send_header=True)
                except OSError:
                    pass
                except Exception as exc:
                    errors.append(exc)

        thread = threading.Thread(target=produce, daemon=True)
        thread.start()
        timestamps = []
        metrics = None
        video_after_metrics = False
        try:
            with receiver:
                receiver.settimeout(6)
                self.assertEqual(exact(receiver, 8), MAGIC_DIAGNOSTICS)
                size, = LENGTH.unpack(exact(receiver, 4))
                self.assertEqual(json.loads(exact(receiver, size))["encoder"], "x264")
                for _ in range(200):
                    kind, size, pts = RECORD.unpack(exact(receiver, RECORD.size))
                    payload = exact(receiver, size)
                    if kind == TELEMETRY_RECORD:
                        self.assertLessEqual(size, MAX_METADATA)
                        metrics = json.loads(payload)
                        self.assertEqual(metrics["sequence"], 1)
                        self.assertGreater(metrics["interval_seconds"], 0)
                        self.assertTrue(all(math.isfinite(value) and value >= 0 for value in metrics.values()))
                    else:
                        self.assertEqual(kind, VIDEO_RECORD)
                        self.assertTrue(payload.startswith(b"\0\0\0\1"))
                        timestamps.append(pts)
                        if metrics is not None:
                            video_after_metrics = True
                            break
        finally:
            receiver.close()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)
        self.assertIsNotNone(metrics)
        self.assertTrue(video_after_metrics)
        self.assertEqual(timestamps, sorted(set(timestamps)))
