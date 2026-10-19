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
TEST_COMPLETE_RECORD = 3
MAX_METADATA = 4096
MAX_FRAME = 8 * 1024 * 1024


def write_header(stream, width, height, fps, source="test-pattern", encoder=None, diagnostics=False,
                 test_id=None, test_duration_seconds=None):
    fields = {"codec": "h264", "width": width, "height": height, "fps": fps, "source": source}
    if encoder is not None:
        fields["encoder"] = encoder
    if test_id is not None or test_duration_seconds is not None:
        if not diagnostics or source != "test-pattern" or not isinstance(test_id, str) or not test_id:
            raise ValueError("Timed diagnostic tests require v2, a test pattern and a test ID")
        if type(test_duration_seconds) is not int or not 1 <= test_duration_seconds <= 3600:
            raise ValueError("Invalid diagnostic test duration")
        fields.update(test_id=test_id, test_duration_seconds=test_duration_seconds)
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
    write_metadata_record(stream, TELEMETRY_RECORD, fields, pts_us)


def write_test_complete(stream, test_id, duration_seconds, elapsed_seconds, pts_us):
    write_metadata_record(stream, TEST_COMPLETE_RECORD, {
        "event": "test_complete", "test_id": test_id,
        "duration_seconds": duration_seconds, "elapsed_seconds": elapsed_seconds,
    }, pts_us)


def write_metadata_record(stream, kind, fields, pts_us):
    payload = json.dumps(fields, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(payload) <= MAX_METADATA:
        raise ValueError("Telemetry too large")
    stream.sendall(RECORD.pack(kind, len(payload), pts_us))
    stream.sendall(payload)
