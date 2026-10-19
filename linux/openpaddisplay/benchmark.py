"""A host-only, real-time encoder benchmark; does not measure Android/USB."""

import json
import time

from .protocol import FRAME, LENGTH, MAGIC
from .video import stream_video


class BenchmarkComplete(Exception):
    pass


class BenchmarkSink:
    """Consume the serializer's header/payload writes without a network queue."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.metadata = None
        self.pending = None
        self.warmup_until = None
        self.started = self.ended = None
        self.frames = self.bytes = 0
        self.first_pts = self.last_pts = None
        self.cpu_started = self.cpu_ended = None

    def sendall(self, data):
        if self.metadata is None:
            if data[:8] != MAGIC:
                raise ValueError("Invalid benchmark session header")
            size, = LENGTH.unpack(data[8:12])
            self.metadata = json.loads(data[12:12 + size])
            self.warmup_until = time.monotonic() + 2
            return
        if self.pending is None:
            self.pending = FRAME.unpack(data)
            return
        size, pts = self.pending
        self.pending = None
        if len(data) != size:
            raise ValueError("Incomplete benchmark access unit")
        now = time.monotonic()
        if now < self.warmup_until:
            return
        if self.started is None:
            self.started = now
            self.cpu_started = time.process_time()
            self.first_pts = pts
        self.frames += 1
        self.bytes += size
        self.last_pts = pts
        if now - self.started >= self.seconds:
            self.ended = now
            self.cpu_ended = time.process_time()
            raise BenchmarkComplete()

    def result(self):
        seconds = self.ended - self.started
        return {
            "scope": "host-only; USB, Android decoding and presentation excluded",
            **self.metadata,
            "seconds": round(seconds, 3),
            "encoded_frames": self.frames,
            "encoded_fps": round((self.frames - 1) / seconds, 2),
            "bitrate_mbps": round(self.bytes * 8 / seconds / 1e6, 2),
            "cpu_percent": round((self.cpu_ended - self.cpu_started) / seconds * 100, 1),
            "pts_span_us": self.last_pts - self.first_pts,
        }


def run_benchmark(args, monitor=None):
    sink = BenchmarkSink(args.benchmark)
    try:
        stream_video(sink, args, monitor, send_header=True)
    except BenchmarkComplete:
        result = sink.result()
        result["pattern"] = args.pattern if args.source == "test-pattern" else None
        print("BENCHMARK " + json.dumps(result, sort_keys=True), flush=True)
        return
    raise RuntimeError("Stream ended before benchmark completed")
