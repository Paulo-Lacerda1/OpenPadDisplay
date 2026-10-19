import json
import os
import re
import shutil
import socket
import subprocess
import threading
import unittest
from unittest.mock import patch

from openpaddisplay.__main__ import parse_args
from openpaddisplay.protocol import FRAME, LENGTH, MAGIC
from openpaddisplay import video
from test_protocol import exact


class EncoderTests(unittest.TestCase):
    def setUp(self):
        try:
            video.load_gst()
        except RuntimeError as exc:
            self.skipTest(str(exc))

    def receive_video(self, encoder):
        args = parse_args(["--width", "320", "--height", "240", "--fps", "30", "--encoder", encoder])
        sender, receiver = socket.socketpair()
        errors = []

        def produce():
            with sender:
                sender.settimeout(3)
                try:
                    video.stream_video(sender, args, send_header=True)
                except OSError:
                    pass
                except Exception as exc:
                    errors.append(exc)

        thread = threading.Thread(target=produce, daemon=True)
        thread.start()
        units = []
        timestamps = []
        try:
            with receiver:
                receiver.settimeout(6)
                self.assertEqual(exact(receiver, 8), MAGIC)
                size, = LENGTH.unpack(exact(receiver, 4))
                metadata = json.loads(exact(receiver, size))
                for _ in range(4):
                    size, pts = FRAME.unpack(exact(receiver, FRAME.size))
                    units.append(exact(receiver, size))
                    timestamps.append(pts)
        finally:
            receiver.close()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), "Encoder thread did not stop on disconnect")
        self.assertFalse(errors, errors)
        types = [unit[0] & 31 for unit in re.split(b"\x00\x00(?:\x00)?\x01", units[0])[1:] if unit]
        self.assertTrue({7, 8, 5}.issubset(types), types)
        self.assertEqual(timestamps, sorted(set(timestamps)))
        return metadata, b"".join(units)

    def test_cpu_stream_advertises_actual_encoder(self):
        metadata, _ = self.receive_video("x264")
        self.assertEqual(metadata["encoder"], "x264")

    def test_auto_fallback_sends_one_correct_header_and_decodable_video(self):
        original = video._stream_pipeline

        def fail_hardware(Gst, connection, args, monitor, encoder, send_header):
            if encoder == "nvenc":
                raise video.EncoderStartupError("simulated driver failure")
            return original(Gst, connection, args, monitor, encoder, send_header)

        with patch.object(video, "encoder_candidates", return_value=["nvenc", "x264"]), \
                patch.object(video, "_stream_pipeline", side_effect=fail_hardware):
            metadata, _ = self.receive_video("auto")
        self.assertEqual(metadata["encoder"], "x264")

    def test_running_encoder_failure_never_switches_bitstream(self):
        args = parse_args([])
        with patch.object(video, "encoder_candidates", return_value=["nvenc", "x264"]), \
                patch.object(video, "_stream_pipeline", side_effect=RuntimeError("running encoder failed")) as encode:
            with self.assertRaisesRegex(RuntimeError, "running encoder failed"):
                video.stream_video(None, args)
        self.assertEqual(encode.call_count, 1)

    def test_explicit_nvenc_never_falls_back_to_cpu(self):
        args = parse_args(["--encoder", "nvenc"])
        with patch.object(video, "encoder_candidates", return_value=["nvenc"]), \
                patch.object(video, "_stream_pipeline", side_effect=video.EncoderStartupError("driver unavailable")) as encode:
            with self.assertRaisesRegex(video.EncoderStartupError, "driver unavailable"):
                video.stream_video(None, args)
        self.assertEqual(encode.call_count, 1)

    @unittest.skipUnless(os.environ.get("OPENPADDISPLAY_TEST_NVENC") == "1", "Set OPENPADDISPLAY_TEST_NVENC=1 on an NVIDIA host")
    def test_hardware_stream_headers_and_decode(self):
        video.load_gst(encoder="nvenc")
        metadata, data = self.receive_video("nvenc")
        self.assertEqual(metadata["encoder"], "nvenc")
        if shutil.which("ffmpeg"):
            result = subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "h264", "-i", "pipe:0", "-f", "framemd5", "pipe:1"],
                input=data, capture_output=True, timeout=10, check=True,
            )
            frames = [line for line in result.stdout.decode().splitlines() if line and not line.startswith("#")]
            self.assertEqual(len(frames), 4)
