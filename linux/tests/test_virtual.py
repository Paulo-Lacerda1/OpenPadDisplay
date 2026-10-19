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
        from openpaddisplay.layout import MonitorLayout
        self.desktop_layout = MonitorLayout(self.bus)
        self.original_layout = self.desktop_layout.state()

    def tearDown(self):
        # Mutter's default hotplug reflow also affects the pre-existing tests.
        # Restore the user's unsaved arrangement after each opt-in test.
        self.desktop_layout.restore(self.original_layout, "__test_monitor_removed__")

    def monitors(self):
        state = self.bus.call_sync(
            "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig", "GetCurrentState", None, None,
            self.Gio.DBusCallFlags.NONE, 5000, None,
        ).unpack()
        return {tuple(monitor[0]): monitor[1] for monitor in state[1]}

    def exercise_monitor(self, fail=False, fps=60, position=None):
        from openpaddisplay.virtual import VirtualMonitor
        from openpaddisplay.layout import positioned_layout
        from openpaddisplay.layout import layout_signature
        before = self.monitors()
        added = set()
        try:
            with VirtualMonitor(position=position) as monitor:
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
                    if position is not None:
                        connector = next(iter(added))[0]
                        current_state = monitor.layout.state()
                        # GNOME can reflow outputs on hotplug. Placement must
                        # use the layout captured before creating the tablet.
                        new_monitor = [item for item in current_state[1] if item[0][0] == connector]
                        new_logical = [row for row in current_state[2] if any(spec[0] == connector for spec in row[5])]
                        before_state = monitor.layout_before
                        desired = (current_state[0], [*before_state[1], *new_monitor],
                                   [*before_state[2], *new_logical], before_state[3])
                        expected = positioned_layout(desired, connector, position)
                        monitor.apply_position()
                        placed = monitor.layout.state()
                        actual = {spec[0]: logical[:5]
                                  for logical in placed[2] for spec in logical[5]}
                        for row in expected:
                            for member in row[5]:
                                self.assertEqual(actual[member[0]], tuple(row[:5]))
                        self.assertTrue(monitor.position_applied)
                        monitor.apply_position()
                        self.assertEqual(monitor.layout.state()[0], placed[0], "Repeated placement changed the layout")
                        # Capture must continue after the compositor moves the output.
                        sample = pipeline.get_by_name("video").emit("try-pull-sample", 5 * self.Gst.SECOND)
                        self.assertIsNotNone(sample, "Capture stopped after positioning")
                    if fail:
                        raise RuntimeError("Simulated consumer failure")
                finally:
                    monitor.prepare_cleanup()
                    pipeline.set_state(self.Gst.State.NULL)
        finally:
            # Mutter schedules output removal after the D-Bus Stop reply.
            deadline = time.monotonic() + 3
            while added & set(self.monitors()) and time.monotonic() < deadline:
                time.sleep(0.05)
            after = self.monitors()
            self.assertFalse(added & set(after), "Virtual output survived source cleanup")
            self.assertTrue(set(before).issubset(after), "An existing output disappeared")
            if position is not None:
                self.assertEqual(layout_signature(monitor.layout.state()), layout_signature(monitor.layout_before),
                                 "Pre-session desktop arrangement was not restored")

    def test_virtual_output_capture_and_removal(self):
        self.exercise_monitor()

    def test_virtual_output_removed_when_consumer_fails(self):
        with self.assertRaisesRegex(RuntimeError, "Simulated consumer failure"):
            self.exercise_monitor(fail=True)

    def test_virtual_output_can_negotiate_144_hz(self):
        self.exercise_monitor(fps=144)

    def test_virtual_output_positions_and_cleanup(self):
        for position in ("left", "right", "above", "below"):
            with self.subTest(position=position):
                self.exercise_monitor(position=position)

    def test_positioned_output_restores_layout_when_consumer_fails(self):
        with self.assertRaisesRegex(RuntimeError, "Simulated consumer failure"):
            self.exercise_monitor(position="left", fail=True)
