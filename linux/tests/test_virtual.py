"""Opt-in desktop tests: these briefly create and remove a real virtual output."""

import os
import time
import unittest

from openpaddisplay.video import load_gst, pipeline_description


@unittest.skipUnless(os.environ.get("OPENPADDISPLAY_TEST_VIRTUAL") == "1",
                     "Set OPENPADDISPLAY_TEST_VIRTUAL=1 inside GNOME Wayland to test real displays")
class VirtualDisplayTests(unittest.TestCase):
    def setUp(self):
        from gi.repository import Gio
        self.Gio = Gio
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.Gst = load_gst(virtual=True)

    def monitors(self):
        state = self.bus.call_sync(
            "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig", "GetCurrentState", None, None,
            self.Gio.DBusCallFlags.NONE, 5000, None,
        ).unpack()
        return {tuple(monitor[0]): monitor[1] for monitor in state[1]}

    def exercise_monitor(self, fail=False, fps=60):
        from openpaddisplay.virtual import VirtualMonitor
        before = self.monitors()
        added = set()
        try:
            with VirtualMonitor() as monitor:
                pipeline = self.Gst.parse_launch(pipeline_description(960, 640, fps, 4000, monitor.node_id))
                try:
                    pipeline.set_state(self.Gst.State.PLAYING)
                    sample = pipeline.get_by_name("video").emit("try-pull-sample", 5 * self.Gst.SECOND)
                    self.assertIsNotNone(sample, "No H.264 sample arrived from the virtual monitor")
                    self.assertGreater(sample.get_buffer().get_size(), 0)
                    active = self.monitors()
                    added = set(active) - set(before)
                    self.assertEqual(len(added), 1, "Expected exactly one additional virtual output")
                    modes = active[next(iter(added))]
                    current = [mode for mode in modes if mode[6].get("is-current")]
                    self.assertEqual(len(current), 1)
                    self.assertEqual(current[0][1:3], (960, 640))
                    self.assertAlmostEqual(current[0][3], fps, delta=0.1)
                    if fail:
                        raise RuntimeError("Simulated consumer failure")
                finally:
                    pipeline.set_state(self.Gst.State.NULL)
        finally:
            # Mutter schedules output removal after the D-Bus Stop reply.
            deadline = time.monotonic() + 3
            while added & set(self.monitors()) and time.monotonic() < deadline:
                time.sleep(0.05)
            after = self.monitors()
            self.assertFalse(added & set(after), "Virtual output survived source cleanup")
            self.assertTrue(set(before).issubset(after), "An existing output disappeared")

    def test_virtual_output_capture_and_removal(self):
        self.exercise_monitor()

    def test_virtual_output_removed_when_consumer_fails(self):
        with self.assertRaisesRegex(RuntimeError, "Simulated consumer failure"):
            self.exercise_monitor(fail=True)

    def test_virtual_output_can_negotiate_144_hz(self):
        self.exercise_monitor(fps=144)
