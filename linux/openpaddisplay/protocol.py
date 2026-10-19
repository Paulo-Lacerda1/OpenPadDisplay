"""Version 1 and opt-in v2 framing; see protocol/README.md and StreamProtocol.kt."""

import json
import struct

MAGIC = b"OPAD0001"
MAGIC_DIAGNOSTICS = b"OPAD0002"
LENGTH = struct.Struct("!I")
FRAME = struct.Struct("!IQ")
RECORD = struct.Struct("!BIQ")
VIDEO_RECORD = 1
TELEMETRY_RECORD = 2
MAX_METADATA = 4096
MAX_FRAME = 8 * 1024 * 1024


def write_header(stream, width, height, fps, source="test-pattern", encoder=None, diagnostics=False):
    fields = {"codec": "h264", "width": width, "height": height, "fps": fps, "source": source}
    if encoder is not None:
        fields["encoder"] = encoder
    metadata = json.dumps(fields).encode("utf-8")
    if len(metadata) > MAX_METADATA:
        raise ValueError("Metadata too large")
    magic = MAGIC_DIAGNOSTICS if diagnostics else MAGIC
    stream.sendall(magic + LENGTH.pack(len(metadata)) + metadata)


def write_frame(stream, payload, pts_us, diagnostics=False):
    if not 0 < len(payload) <= MAX_FRAME:
        raise ValueError("Invalid access unit size")
    header = RECORD.pack(VIDEO_RECORD, len(payload), pts_us) if diagnostics else FRAME.pack(len(payload), pts_us)
    stream.sendall(header)
    stream.sendall(payload)


def write_telemetry(stream, fields, pts_us):
    payload = json.dumps(fields, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(payload) <= MAX_METADATA:
        raise ValueError("Telemetry too large")
    stream.sendall(RECORD.pack(TELEMETRY_RECORD, len(payload), pts_us))
    stream.sendall(payload)
