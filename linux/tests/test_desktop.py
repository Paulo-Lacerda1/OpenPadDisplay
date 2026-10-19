"""Opt-in launcher tests; run under Xvfb without starting a stream."""

import os
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get("OPENPADDISPLAY_TEST_DESKTOP") == "1",
                     "Set OPENPADDISPLAY_TEST_DESKTOP=1 under Xvfb for launcher tests")
class DesktopPositionTests(unittest.TestCase):
    def test_position_selection_persistence_command_and_session_controls(self):
        from openpaddisplay.desktop import DisplayApplication
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            app = DisplayApplication()
            app.set_application_id("org.openpaddisplay.PositionTest")
            app.register(None)
            app.do_activate()
            try:
                with patch("openpaddisplay.desktop.subprocess.Popen") as launch, \
                        patch("openpaddisplay.desktop.threading.Thread"):
                    for position, button in zip(("left", "right", "above", "below"), app.position_buttons):
                        button.set_active(True)
                        self.assertEqual(app.position, position)
                        self.assertEqual(app.preview.position, position)
                        from openpaddisplay.preferences import load_position
                        self.assertEqual(load_position(), position)
                        app.on_toggle(None)
                        command = launch.call_args.args[0]
                        self.assertEqual(command[command.index("--position") + 1], position)
                        self.assertIn("--diagnostics", command)
                        self.assertFalse(app.diagnostics.get_sensitive())
                        self.assertTrue(all(not choice.get_sensitive() for choice in app.position_buttons))
                        app.on_finished(app.process, 0)
                        self.assertTrue(all(choice.get_sensitive() for choice in app.position_buttons))
                        self.assertFalse(app.diagnostics.get_sensitive())
                    launch.side_effect = OSError("test startup error")
                    app.on_toggle(None)
                    self.assertIsNone(app.process)
                    self.assertTrue(all(choice.get_sensitive() for choice in app.position_buttons))
                self.check_metrics_toggle_is_live_confirmed_and_ignores_stale_replies(app)
                reloaded = DisplayApplication()
                self.assertEqual(reloaded.position, "below")
            finally:
                app.window.destroy()
                app.quit()

    def check_metrics_toggle_is_live_confirmed_and_ignores_stale_replies(self, app):
        from gi.repository import GLib
        with patch("openpaddisplay.desktop.subprocess.Popen"), \
                patch("openpaddisplay.desktop.threading.Thread") as worker:
            app.on_toggle(None)
            process = app.process
            self.assertFalse(app.diagnostics.get_sensitive())
            app.on_output("Streaming with nvenc")
            revision = app.metrics_revision
            app.on_metrics_applied(process, revision, False, None)
            self.assertTrue(app.diagnostics.get_sensitive())
            app.activate_action("metrics", GLib.Variant("b", True))
            self.assertFalse(app.diagnostics.get_sensitive())
            with patch("openpaddisplay.desktop.control_tablet", return_value={"visible": True}) as control, \
                    patch("openpaddisplay.desktop.GLib.idle_add") as idle:
                worker.call_args.kwargs["target"]()
                control.assert_called_once_with("metrics", visible=True)
                app.on_metrics_applied(*idle.call_args.args[1:])
            self.assertIs(app.process, process)
            self.assertTrue(app.diagnostics.get_active())
            app.activate_action("metrics", GLib.Variant("b", False))
            app.on_metrics_applied(process, app.metrics_revision, False, "USB indisponível")
            self.assertTrue(app.diagnostics.get_active())  # Failed hide must not claim success.
            app.diagnostics.set_active(False)
            revision = app.metrics_revision
            app.on_output("Session ended: disconnected")
            app.on_metrics_applied(process, revision, False, None)
            self.assertTrue(app.diagnostics.get_sensitive())  # USB overlay controls survive a video interruption.
            app.diagnostics.set_active(True)
            app.on_metrics_applied(process, app.metrics_revision, True, None)
            app.diagnostics.set_active(False)
            app.on_metrics_applied(process, app.metrics_revision, False, None)
            self.assertFalse(app.metrics_applied)
            app.on_finished(process, 0)
            self.assertFalse(app.diagnostics.get_active())
