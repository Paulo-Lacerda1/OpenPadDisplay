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
                        self.assertTrue(all(not choice.get_sensitive() for choice in app.position_buttons))
                        app.on_finished(app.process, 0)
                        self.assertTrue(all(choice.get_sensitive() for choice in app.position_buttons))
                    launch.side_effect = OSError("test startup error")
                    app.on_toggle(None)
                    self.assertIsNone(app.process)
                    self.assertTrue(all(choice.get_sensitive() for choice in app.position_buttons))
                reloaded = DisplayApplication()
                self.assertEqual(reloaded.position, "below")
            finally:
                app.window.destroy()
                app.quit()
