import argparse
import socket
import sys
from contextlib import nullcontext

from .protocol import write_header
from .video import load_gst, pipeline_description, stream_video


def positive(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("Must be positive")
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="OpenPadDisplay USB video server for Android tablets")
    parser.add_argument("--source", choices=("test-pattern", "virtual"), default="test-pattern",
                        help="Use a test pattern or a GNOME Wayland extended desktop")
    parser.add_argument("--port", type=positive, default=27183)
    parser.add_argument("--width", type=positive, default=1920)
    parser.add_argument("--height", type=positive, default=1280)
    parser.add_argument("--fps", type=positive, default=60, help="Requested source rate, up to 144; not guaranteed")
    parser.add_argument("--bitrate", type=positive, default=12000, help="H.264 bitrate in kbit/s")
    parser.add_argument("--dry-run", action="store_true", help="Print the pipeline without opening a socket")
    args = parser.parse_args(argv)
    if args.port > 65535 or args.fps > 144:
        parser.error("Port must be <= 65535 and FPS <= 144")
    if args.width % 2 or args.height % 2 or max(args.width, args.height) > 4096:
        parser.error("Dimensions must be even and <= 4096")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.dry_run:
        print(pipeline_description(args.width, args.height, args.fps, args.bitrate,
                                   node_id=0 if args.source == "virtual" else None))
        if args.source == "virtual":
            print("# node 0 is a placeholder; the real node is allocated by Mutter on connection")
        return 0
    try:
        load_gst(virtual=args.source == "virtual")
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", args.port))
            listener.listen(1)
            print(f"OpenPadDisplay listening on 127.0.0.1:{args.port}; source={args.source}", flush=True)
            print(f"Run: adb reverse tcp:27183 tcp:{args.port} — then open the Android app", flush=True)
            while True:
                connection, _ = listener.accept()
                with connection:
                    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    connection.settimeout(3)
                    try:
                        if args.source == "virtual":
                            from .virtual import VirtualMonitor
                            source = VirtualMonitor()
                        else:
                            source = nullcontext(None)
                        with source as monitor:
                            write_header(connection, args.width, args.height, args.fps, source=args.source)
                            stream_video(connection, args, monitor)
                    except (OSError, RuntimeError, ValueError) as exc:
                        print(f"Session ended: {exc}; waiting for reconnection", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
