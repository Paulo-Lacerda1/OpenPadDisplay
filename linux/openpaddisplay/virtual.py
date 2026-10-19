"""GNOME Mutter virtual output owned by a private, short-lived D-Bus connection."""

import os
import threading


BUS_NAME = "org.gnome.Mutter.ScreenCast"
ROOT = "/org/gnome/Mutter/ScreenCast"
SESSION_INTERFACE = BUS_NAME + ".Session"
STREAM_INTERFACE = BUS_NAME + ".Stream"


class VirtualMonitor:
    """Keep the D-Bus owner alive until the PipeWire consumer has stopped.

    Mutter creates the actual output when PipeWire negotiates its size/rate.
    Disconnecting this private bus connection also releases the session if Stop
    fails or the process is terminated. No saved monitor configuration is edited.
    """

    def __init__(self, timeout=10):
        self.timeout = timeout
        self.connection = None
        self.session_path = None
        self.node_id = None
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.loop = None
        self.thread = None
        self.subscriptions = []

    def _call(self, path, interface, method, parameters=None):
        return self.connection.call_sync(
            BUS_NAME, path, interface, method, parameters, None,
            self.Gio.DBusCallFlags.NONE, 5000, None,
        )

    def _on_node(self, _connection, _sender, _path, _interface, _signal, parameters, _data):
        self.node_id = parameters.unpack()[0]
        self.ready.set()

    def _on_closed(self, *_args):
        self.closed.set()
        self.ready.set()

    def __enter__(self):
        from gi.repository import Gio, GLib

        self.Gio = Gio
        self.GLib = GLib
        if os.environ.get("XDG_SESSION_TYPE") != "wayland":
            raise RuntimeError("The virtual source requires a GNOME Wayland session")
        address = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        if not address:
            raise RuntimeError("Session D-Bus address missing; run from your GNOME desktop terminal")
        context = GLib.MainContext.new()
        self.loop = GLib.MainLoop.new(context, False)
        try:
            context.push_thread_default()
            try:
                self.connection = Gio.DBusConnection.new_for_address_sync(
                    address,
                    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                    None, None,
                )
                self.connection.set_exit_on_close(False)
                self.session_path = self._call(
                    ROOT, BUS_NAME, "CreateSession", GLib.Variant("(a{sv})", ({},)),
                ).unpack()[0]
                stream_path = self._call(
                    self.session_path, SESSION_INTERFACE, "RecordVirtual",
                    GLib.Variant("(a{sv})", ({
                        "cursor-mode": GLib.Variant("u", 1),
                        "is-platform": GLib.Variant("b", True),
                    },)),
                ).unpack()[0]
                self.subscriptions.append(self.connection.signal_subscribe(
                    BUS_NAME, STREAM_INTERFACE, "PipeWireStreamAdded", stream_path,
                    None, Gio.DBusSignalFlags.NONE, self._on_node, None,
                ))
                self.subscriptions.append(self.connection.signal_subscribe(
                    BUS_NAME, SESSION_INTERFACE, "Closed", self.session_path,
                    None, Gio.DBusSignalFlags.NONE, self._on_closed, None,
                ))
                self._call(self.session_path, SESSION_INTERFACE, "Start")
            finally:
                context.pop_thread_default()
            self.thread = threading.Thread(target=self.loop.run, name="Mutter-D-Bus", daemon=True)
            self.thread.start()
            if not self.ready.wait(self.timeout):
                raise RuntimeError("Mutter did not publish a PipeWire node within the startup timeout")
            if self.closed.is_set() or self.node_id is None:
                raise RuntimeError("Mutter closed the virtual monitor session during startup")
            print(f"Mutter virtual stream ready: PipeWire node {self.node_id}", flush=True)
            return self
        except GLib.Error as exc:
            self.close()
            raise RuntimeError(f"GNOME virtual monitor: {exc.message}") from exc
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.connection:
            for subscription in self.subscriptions:
                self.connection.signal_unsubscribe(subscription)
            self.subscriptions.clear()
            try:
                if self.session_path and not self.closed.is_set():
                    self._call(self.session_path, SESSION_INTERFACE, "Stop")
            except self.GLib.Error:
                pass  # Closing the private bus owner below is the cleanup fallback.
            try:
                self.connection.close_sync(None)
            except self.GLib.Error:
                pass
            self.connection = None
        self.closed.set()
        if self.loop:
            self.loop.quit()
        if self.thread:
            self.thread.join(timeout=2)

    def __exit__(self, *_args):
        self.close()
