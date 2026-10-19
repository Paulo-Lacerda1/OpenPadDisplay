"""Timed RGB tests must finish once, explicitly, after real video is transmitted."""
import contextlib
import io
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch

from openpaddisplay.__main__ import main, parse_args
from openpaddisplay.protocol import (LENGTH, MAGIC_DIAGNOSTICS, RECORD, TEST_COMPLETE_RECORD,
                                    VIDEO_RECORD, write_header)
from openpaddisplay.video import load_gst, pipeline_description, stream_video
from test_protocol import exact


class TimedStreamTests(unittest.TestCase):
    def test_timed_header_cannot_be_accidentally_sent_to_a_legacy_client(self):
        class Destination:
            def __init__(self):
                self.data = bytearray()

            def sendall(self, data):
                self.data.extend(data)

        for fields in ({"diagnostics": False}, {"diagnostics": True, "source": "virtual"},
                       {"diagnostics": True, "test_duration_seconds": None}):
            values = {"test_id": "test123", "test_duration_seconds": 10, **fields}
            destination = Destination()
            with self.assertRaises(ValueError):
                write_header(destination, 320, 240, 30, **values)
            self.assertFalse(destination.data)

    def test_duration_only_allows_bounded_one_shot_test_sources(self):
        self.assertEqual(parse_args(["--duration", "10", "--pattern", "scroll"]).duration, 10)
        self.assertIsNone(parse_args([]).duration)
        for args in (["--duration", "0"], ["--duration", "3601"],
                     ["--duration", "10", "--source", "virtual"],
                     ["--duration", "10", "--benchmark", "2"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(args)

    def test_timed_server_exits_after_one_session_or_failure(self):
        for failure in (None, OSError("USB disconnected")):
            with patch("openpaddisplay.__main__.load_gst"), \
                    patch("openpaddisplay.__main__.socket.socket") as socket_factory, \
                    patch("openpaddisplay.__main__.stream_video", side_effect=failure,
                          return_value={"duration_seconds": 1}) as stream, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                listener = socket_factory.return_value.__enter__.return_value
                listener.accept.return_value = (socket.socket(), ("127.0.0.1", 12345))
                self.assertEqual(main(["--duration", "1"]), 1 if failure else 0)
                listener.settimeout.assert_called_once_with(15)
                listener.accept.assert_called_once()
                stream.assert_called_once()

    def test_scroll_has_horizontal_motion_in_the_color_bars(self):
        try:
            Gst = load_gst()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        source = pipeline_description(320, 240, 30, 1000, pattern="scroll").split("identity", 1)[0]
        source = source.replace("video/x-raw,", "video/x-raw,format=RGB,", 1)
        pipeline = Gst.parse_launch(source + "appsink name=frames sync=false")
        try:
            pipeline.set_state(Gst.State.PLAYING)
            sink = pipeline.get_by_name("frames")
            frames = []
            for _ in range(2):
                sample = sink.emit("try-pull-sample", 3 * Gst.SECOND)
                self.assertIsNotNone(sample)
                buffer = sample.get_buffer()
                frames.append(buffer.extract_dup(0, buffer.get_size()))
            # The upper bar rows have no random TV noise: a changed row proves
            # horizontal movement, rather than the SMPTE noise patch animating.
            first, second = (frame[20 * 320 * 3:21 * 320 * 3] for frame in frames)
            self.assertNotEqual(first, second)
            colors = {first[i:i + 3] for i in range(0, len(first), 3)}
            for channel in range(3):
                self.assertTrue(any(color[channel] >= 180 and
                                    all(color[other] < 20 for other in range(3) if other != channel)
                                    for color in colors), f"Missing RGB bar {channel}")
        finally:
            pipeline.set_state(Gst.State.NULL)

    def test_real_timed_stream_sends_matching_completion_before_eof_and_stops(self):
        try:
            load_gst()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        args = parse_args(["--duration", "1", "--diagnostics", "--encoder", "x264",
                           "--pattern", "scroll", "--width", "320", "--height", "240", "--fps", "30"])
        sender, receiver = socket.socketpair()
        errors = []

        def produce():
            try:
                with sender:
                    sender.settimeout(3)
                    stream_video(sender, args, send_header=True)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=produce, daemon=True)
        started = time.monotonic()
        thread.start()
        timestamps = []
        completion = None
        try:
            with receiver:
                receiver.settimeout(5)
                self.assertEqual(exact(receiver, 8), MAGIC_DIAGNOSTICS)
                size, = LENGTH.unpack(exact(receiver, LENGTH.size))
                metadata = json.loads(exact(receiver, size))
                self.assertEqual(metadata["test_duration_seconds"], 1)
                self.assertTrue(metadata["test_id"])
                while completion is None:
                    kind, size, pts = RECORD.unpack(exact(receiver, RECORD.size))
                    payload = exact(receiver, size)
                    if kind == VIDEO_RECORD:
                        timestamps.append(pts)
                    elif kind == TEST_COMPLETE_RECORD:
                        completion = json.loads(payload)
                        self.assertEqual(pts, timestamps[-1])
                self.assertEqual(receiver.recv(1), b"")
        finally:
            receiver.close()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)
        self.assertEqual(completion["test_id"], metadata["test_id"])
        self.assertEqual(completion["duration_seconds"], 1)
        self.assertGreaterEqual(completion["elapsed_seconds"], 1)
        self.assertLess(time.monotonic() - started, 4)
        self.assertGreaterEqual(len(timestamps), 20)
        self.assertEqual(timestamps, sorted(set(timestamps)))
