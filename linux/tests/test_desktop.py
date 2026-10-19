"""Opt-in launcher tests; run under Xvfb without starting a stream."""

import os
import signal
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(os.environ.get("OPENPADDISPLAY_TEST_DESKTOP") == "1",
                     "Set OPENPADDISPLAY_TEST_DESKTOP=1 under Xvfb for launcher tests")
class DesktopPositionTests(unittest.TestCase):
    def test_guided_test_command_uses_animated_pattern_and_duration(self):
        from openpaddisplay.desktop import stream_command

        command = stream_command(
            Path("/tmp/OpenPadDisplay"), "1440x960", "120",
            diagnostics=True, source="test-pattern", pattern="scroll", duration=10,
        )
        self.assertIn("--source", command)
        self.assertEqual(command[command.index("--source") + 1], "test-pattern")
        self.assertEqual(command[command.index("--pattern") + 1], "scroll")
        self.assertEqual(command[command.index("--duration") + 1], "10")
        self.assertIn("--diagnostics", command)
        self.assertNotIn("--position", command)

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
            finally:
                if app.process is not None:
                    app.on_finished(app.process, 0)
                app.window.destroy()
                app.quit()

    def check_guided_transitions(self, app):
        class FakeProcess:
            def __init__(self, exit_code=0):
                self.returncode = None
                self.exit_code = exit_code
                self.pid = 123
                self.wait_calls = 0
                self.stdout = StringIO("")

            def wait(self, timeout=None):
                self.wait_calls += 1
                self.returncode = self.exit_code
                return self.returncode

            def poll(self):
                return self.returncode

        for scenario in ("success", "host_failure", "no_result", "bad_json", "wrong_tablet",
                         "cancel", "stop", "close", "restore_failure", "late_stop"):
            with self.subTest(scenario=scenario):
                original = FakeProcess()
                test = FakeProcess(1 if scenario == "host_failure" else 0)
                restored = FakeProcess()
                app.process = original
                app.closing = app.stopping = False
                app.connected = True
                app.rate.set_active_id("120")
                app.resolution.set_active_id("1440x960")
                app.diagnostics.set_sensitive(False)
                app.diagnostics.set_active(True)
                app.button.set_label("Desligar tablet")
                app.pending_test_result = None
                position = app.position
                response = {"test_id": "wrong" if scenario == "wrong_tablet" else "abc",
                            "test_state": "completed", "test_result": "Sem limitação evidente"}
                queued = []

                def idle(callback, *args):
                    if scenario == "late_stop":
                        queued.append((callback, args))
                    else:
                        callback(*args)

                def read(process, cancelled):
                    self.assertIs(process, test)
                    if scenario == "bad_json":
                        raise ValueError("JSON inválido")
                    if scenario == "cancel":
                        app.cancel_guided_test()
                    elif scenario == "stop":
                        app.stop()
                    elif scenario == "close":
                        app.on_close(None, None)
                    return None if scenario == "no_result" else {"test_id": "abc", "duration_seconds": 10}

                with patch("openpaddisplay.desktop.subprocess.Popen", side_effect=[
                        test, OSError("Restauro falhado") if scenario == "restore_failure" else restored]) as launch, \
                        patch("openpaddisplay.desktop.threading.Thread") as thread, \
                        patch("openpaddisplay.desktop.control_tablet", return_value=response), \
                        patch("openpaddisplay.desktop.GLib.idle_add", side_effect=idle), \
                        patch("openpaddisplay.desktop.GLib.timeout_add_seconds"), \
                        patch.object(app, "send_signal"), \
                        patch.object(app, "run_test_process", side_effect=read), \
                        patch.object(app, "show_test_result") as show_result, \
                        patch.object(app.window, "destroy") as destroy, patch.object(app, "quit") as quit_app:
                    app.start_guided_test()
                    worker = thread.call_args.kwargs["target"]
                    app.position = "above" if position != "above" else "left"
                    worker()
                    if scenario == "late_stop":
                        app.stop()
                        for callback, args in queued:
                            callback(*args)
                    command = launch.call_args_list[0].args[0]
                    self.assertEqual(command[command.index("--source") + 1], "test-pattern")
                    self.assertEqual(command[command.index("--pattern") + 1], "scroll")
                    self.assertEqual(command[command.index("--duration") + 1], "10")
                    self.assertNotIn("--position", command)
                    self.assertGreaterEqual(test.wait_calls, 1)
                    self.assertIsNone(app.test_cancel)
                    self.assertFalse(app.test_transition)
                    if scenario in ("stop", "close", "late_stop", "restore_failure"):
                        self.assertIsNone(app.process)
                        self.assertEqual(app.button.get_label(), "Ligar tablet")
                        self.assertTrue(app.rate.get_sensitive())
                        self.assertTrue(all(b.get_sensitive() for b in app.position_buttons))
                        self.assertFalse(app.diagnostics.get_active())
                        self.assertIsNone(app.pending_test_result)
                        if scenario == "close":
                            destroy.assert_called_once()
                            quit_app.assert_called_once()
                        if scenario != "restore_failure":
                            self.assertEqual(launch.call_count, 1)
                    else:
                        self.assertIs(app.process, restored)
                        self.assertFalse(app.rate.get_sensitive())
                        self.assertFalse(app.resolution.get_sensitive())
                        self.assertTrue(all(not b.get_sensitive() for b in app.position_buttons))
                        restore_command = launch.call_args_list[1].args[0]
                        self.assertEqual(restore_command[restore_command.index("--position") + 1], position)
                        self.assertEqual(restore_command[restore_command.index("--fps") + 1], "120")
                        self.assertTrue(app.diagnostics.get_active())
                        if scenario == "cancel":
                            self.assertIsNone(app.pending_test_result)
                        else:
                            self.assertIsInstance(app.pending_test_result, str)
                            app.on_output("Streaming with nvenc", restored)
                            show_result.assert_called_once()
                app.position = position
                app.process = None
                app.closing = app.stopping = False

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
