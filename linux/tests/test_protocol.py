import contextlib
import io
import json
import re
import socket
import threading
import unittest

from openpaddisplay.__main__ import parse_args
from openpaddisplay.protocol import FRAME, LENGTH, MAGIC, MAX_FRAME, write_frame, write_header
from openpaddisplay.video import load_gst, stream_video


def exact(stream, size):
    result = bytearray()
    while len(result) < size:
        chunk = stream.recv(size - len(result))
        if not chunk:
            raise EOFError("Truncated stream")
        result.extend(chunk)
    return bytes(result)


class ProtocolTests(unittest.TestCase):
    def test_wire_roundtrip_and_timestamp(self):
        left, right = socket.socketpair()
        with left, right:
            right.settimeout(2)
            write_header(left, 1920, 1280, 144)
            self.assertEqual(exact(right, 8), MAGIC)
            size, = LENGTH.unpack(exact(right, 4))
            metadata = json.loads(exact(right, size))
            self.assertEqual(metadata, {"width": 1920, "height": 1280, "fps": 144,
                                        "codec": "h264", "source": "test-pattern"})
            payload = b"\0\0\0\1\x65\x01\x02"
            write_frame(left, payload, 3_600_000_000_000)
            size, pts = FRAME.unpack(exact(right, FRAME.size))
            self.assertEqual(pts, 3_600_000_000_000)
            self.assertEqual(exact(right, size), payload)

    def test_rejects_invalid_frames_without_writing(self):
        class NoWrites:
            def sendall(self, data):
                raise AssertionError("Invalid frame reached transport")
        for payload in (b"", bytes(MAX_FRAME + 1)):
            with self.assertRaises(ValueError):
                write_frame(NoWrites(), payload, 0)

    def test_mode_validation(self):
        self.assertEqual(parse_args(["--fps", "144"]).fps, 144)
        for argv in (["--width", "1919"], ["--fps", "145"], ["--fps", "0"], ["--port", "65536"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(argv)


class GStreamerTests(unittest.TestCase):
    def test_encoded_access_units_and_disconnect_cleanup(self):
        try:
            load_gst()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        args = parse_args(["--width", "320", "--height", "240", "--fps", "30"])
        sender, receiver = socket.socketpair()
        errors = []

        def produce():
            with sender:
                sender.settimeout(2)
                try:
                    stream_video(sender, args)
                except OSError:
                    pass  # Expected when the receiver disconnects.
                except Exception as exc:
                    errors.append(exc)

        thread = threading.Thread(target=produce, daemon=True)
        thread.start()
        timestamps = []
        try:
            with receiver:
                receiver.settimeout(5)
                for index in range(4):
                    size, pts = FRAME.unpack(exact(receiver, FRAME.size))
                    self.assertTrue(0 < size <= MAX_FRAME)
                    data = exact(receiver, size)
                    self.assertTrue(data.startswith(b"\0\0\0\1"))
                    if index == 0:
                        types = [unit[0] & 31 for unit in re.split(b"\x00\x00(?:\x00)?\x01", data)[1:] if unit]
                        self.assertTrue({7, 8, 5}.issubset(types), types)
                    timestamps.append(pts)
        finally:
            receiver.close()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), "Pipeline did not stop after disconnect")
        self.assertFalse(errors, errors)
        self.assertEqual(timestamps, sorted(set(timestamps)))
        for before, after in zip(timestamps, timestamps[1:]):
            self.assertAlmostEqual(after - before, 1_000_000 / 30, delta=2)


if __name__ == "__main__":
    unittest.main()
