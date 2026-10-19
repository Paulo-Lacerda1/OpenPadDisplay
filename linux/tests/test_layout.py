import copy
import contextlib
import io
import unittest
from unittest.mock import Mock

from openpaddisplay.__main__ import parse_args, source_context
from openpaddisplay.layout import LayoutError, MonitorLayout, positioned_layout
from openpaddisplay.layout import configuration_rows, layout_signature, snapshot_state
from openpaddisplay.virtual import VirtualMonitor


def monitor(connector, width, height, *, x=0, y=0, scale=1., transform=0, primary=False):
    spec = (connector, "Vendor", "Model", connector)
    modes = [(f"{width}x{height}@60", width, height, 60., 1., [1., 2.], {"is-current": True})]
    return (spec, modes, {"is-underscanning": False}), (x, y, scale, transform, primary, [spec], {})


def state(*outputs, layout_mode=1):
    return (17, [item[0] for item in outputs], [item[1] for item in outputs],
            {"layout-mode": layout_mode, "supports-changing-layout-mode": True})


def rows_by_connector(rows):
    return {member[0]: row for row in rows for member in row[5]}


class LayoutTests(unittest.TestCase):
    def test_four_positions_preserve_mode_primary_scale_and_transform(self):
        original = state(monitor("eDP-1", 1920, 1080, primary=True),
                         monitor("Meta-1", 960, 640, x=1920))
        snapshot = copy.deepcopy(original)
        expected = {
            "right": ((0, 0), (1920, 0)), "left": ((960, 0), (0, 0)),
            "above": ((0, 640), (0, 0)), "below": ((0, 0), (0, 1080)),
        }
        for position, (pc, tablet) in expected.items():
            with self.subTest(position=position):
                rows = rows_by_connector(positioned_layout(original, "Meta-1", position))
                self.assertEqual(tuple(rows["eDP-1"][:2]), pc)
                self.assertEqual(tuple(rows["Meta-1"][:2]), tablet)
                self.assertEqual(rows["eDP-1"][2:5], [1., 0, True])
                self.assertEqual(rows["eDP-1"][5], [("eDP-1", "1920x1080@60", {"enable_underscanning": False})])
        self.assertEqual(original, snapshot)

    def test_scaled_rotated_and_physical_layout_dimensions(self):
        outputs = (monitor("eDP-1", 3840, 2160, scale=2., transform=1, primary=True),
                   monitor("Meta-1", 960, 640, x=4000, scale=2.))
        rows = rows_by_connector(positioned_layout(state(*outputs), "Meta-1", "right"))
        self.assertEqual(rows["Meta-1"][:2], [1080, 0])
        rows = rows_by_connector(positioned_layout(state(*outputs), "Meta-1", "left"))
        self.assertEqual(rows["eDP-1"][0], 480)
        rows = rows_by_connector(positioned_layout(state(*outputs, layout_mode=2), "Meta-1", "right"))
        self.assertEqual(rows["Meta-1"][:2], [2160, 0])

    def test_multiple_displays_stay_together_and_share_an_edge(self):
        original = state(monitor("eDP-1", 1920, 1080, x=1920, y=1440, primary=True),
                         monitor("HDMI-1", 2560, 1440, x=1460),
                         monitor("Meta-1", 960, 640, x=5000))
        for position in ("left", "right", "above", "below"):
            with self.subTest(position=position):
                rows = rows_by_connector(positioned_layout(original, "Meta-1", position))
                laptop, external, tablet = (rows[key] for key in ("eDP-1", "HDMI-1", "Meta-1"))
                self.assertEqual((laptop[0] - external[0], laptop[1] - external[1]), (460, 1440))
                if position == "right":
                    self.assertEqual(tablet[:2], [external[0] + 2560, external[1]])
                elif position == "left":
                    self.assertEqual(tablet[:2], [external[0] - 960, external[1]])
                elif position == "above":
                    self.assertEqual(tablet[:2], [external[0], external[1] - 640])
                else:
                    self.assertEqual(tablet[:2], [laptop[0], laptop[1] + 1080])

    def test_rejects_missing_or_mirrored_tablet_and_invalid_position(self):
        original = state(monitor("eDP-1", 1920, 1080, primary=True), monitor("Meta-1", 960, 640))
        for connector, position in (("absent", "left"), ("Meta-1", "unknown")):
            with self.assertRaises(LayoutError):
                positioned_layout(original, connector, position)
        mirrored = copy.deepcopy(original)
        mirrored[2][1][5].append(mirrored[1][0][0])
        with self.assertRaises(LayoutError):
            positioned_layout(mirrored, "Meta-1", "left")

    def test_dbus_uses_temporary_method_and_ignores_existing_virtual_outputs(self):
        original = state(monitor("eDP-1", 1920, 1080, primary=True),
                         monitor("Meta-0", 960, 640, x=1920),
                         monitor("Meta-1", 960, 640, x=2880))
        bus = Mock()
        bus.call_sync.return_value.unpack.return_value = original
        layout = MonitorLayout(bus)
        before = (original[0], original[1][:-1], original[2][:-1], original[3])
        self.assertEqual(layout.place(before, "right"), "Meta-1")
        call = bus.call_sync.call_args.args
        self.assertEqual(call[3], "ApplyMonitorsConfig")
        serial, method, rows, _ = call[4].unpack()
        self.assertEqual((serial, method), (17, 1))
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows_by_connector(rows)["eDP-1"][4])

    def test_dbus_rejects_ambiguous_new_virtual_outputs_without_applying(self):
        original = state(monitor("eDP-1", 1920, 1080, primary=True),
                         monitor("Meta-0", 960, 640), monitor("Meta-1", 960, 640))
        bus = Mock()
        bus.call_sync.return_value.unpack.return_value = original
        before = (original[0], original[1][:1], original[2][:1], original[3])
        with self.assertRaises(LayoutError):
            MonitorLayout(bus).place(before, "left")
        self.assertEqual(bus.call_sync.call_count, 1)

    def test_cli_only_accepts_position_for_virtual_sources(self):
        self.assertIsNone(parse_args([]).position)
        args = parse_args(["--source", "virtual", "--position", "left"])
        self.assertEqual(args.position, "left")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["--position", "left"])
        with source_context("test-pattern", None) as virtual:
            self.assertIsNone(virtual)

    def test_snapshot_preserves_pre_hotplug_coordinates_and_modes(self):
        before = state(monitor("eDP-1", 1920, 1080, x=460, y=1440, primary=True),
                       monitor("HDMI-1", 2560, 1440))
        reflowed = state(monitor("eDP-1", 1920, 1080, primary=True),
                          monitor("HDMI-1", 2560, 1440, x=1920))
        restored = snapshot_state(reflowed, before)
        self.assertEqual(layout_signature(restored), layout_signature(before))
        rows = rows_by_connector(configuration_rows(restored))
        self.assertEqual(rows["eDP-1"][:2], [460, 1440])
        changed = state(monitor("eDP-1", 1920, 1080, primary=True))
        with self.assertRaises(LayoutError):
            snapshot_state(changed, before)

    def test_cleanup_restores_only_if_the_user_has_not_rearranged_displays(self):
        original = state(monitor("eDP-1", 1920, 1080, primary=True), monitor("Meta-1", 960, 640, x=1920))
        for changed_by_user in (False, True):
            with self.subTest(changed_by_user=changed_by_user):
                virtual = VirtualMonitor(position="right")
                virtual.layout = Mock()
                virtual.position_applied = True
                virtual.position_connector = "Meta-1"
                virtual.layout_before = (original[0], original[1][:-1], original[2][:-1], original[3])
                virtual.applied_signature = layout_signature(original)
                current = copy.deepcopy(original)
                if changed_by_user:
                    row = list(current[2][1])
                    row[1] = 100
                    current[2][1] = row
                virtual.layout.state.return_value = current
                virtual.prepare_cleanup()
                virtual.close()
                self.assertEqual(virtual.layout.restore.call_count, 0 if changed_by_user else 1)

    def test_retries_stale_serial_with_fresh_state(self):
        from gi.repository import Gio
        original = state(monitor("eDP-1", 1920, 1080, primary=True), monitor("Meta-1", 960, 640, x=1920))
        before = (original[0], original[1][:-1], original[2][:-1], original[3])
        bus = Mock()
        serials = []

        def call(*args):
            if args[3] == "GetCurrentState":
                result = Mock()
                result.unpack.return_value = (17 + len(serials), *original[1:])
                return result
            serials.append(args[4].unpack()[0])
            if len(serials) == 1:
                raise Gio.DBusError.new_for_dbus_error("org.freedesktop.DBus.Error.AccessDenied", "stale serial")

        bus.call_sync.side_effect = call
        MonitorLayout(bus).place(before, "above")
        self.assertEqual(serials, [17, 18])

    def test_failed_placement_also_restores_automatic_hotplug_reflow(self):
        original = state(monitor("eDP-1", 1920, 1080, primary=True), monitor("Meta-1", 960, 640, x=1920))
        virtual = VirtualMonitor(position="left")
        virtual.layout_before = (original[0], original[1][:-1], original[2][:-1], original[3])
        virtual.layout = Mock()
        virtual.layout.place.side_effect = LayoutError("configuration rejected")
        virtual.layout.state.return_value = original
        with self.assertRaises(LayoutError):
            virtual.apply_position()
        virtual.prepare_cleanup()
        virtual.close()
        virtual.layout.restore.assert_called_once_with(virtual.layout_before, "Meta-1")

