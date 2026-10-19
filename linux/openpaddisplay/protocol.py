"""Version 1 framing. Keep in sync with protocol/README.md and StreamProtocol.kt."""

import json
import struct

MAGIC = b"OPAD0001"
LENGTH = struct.Struct("!I")
FRAME = struct.Struct("!IQ")
MAX_METADATA = 4096
MAX_FRAME = 8 * 1024 * 1024


def write_header(stream, width, height, fps, source="test-pattern"):
    metadata = json.dumps({"codec": "h264", "width": width, "height": height,
                           "fps": fps, "source": source}).encode("utf-8")
    if len(metadata) > MAX_METADATA:
        raise ValueError("Metadata too large")
    stream.sendall(MAGIC + LENGTH.pack(len(metadata)) + metadata)


def write_frame(stream, payload, pts_us):
    if not 0 < len(payload) <= MAX_FRAME:
        raise ValueError("Invalid access unit size")
    stream.sendall(FRAME.pack(len(payload), pts_us))
    stream.sendall(payload)
