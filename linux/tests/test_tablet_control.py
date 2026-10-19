import base64
import json
import subprocess
import unittest
from unittest.mock import patch

from openpaddisplay.tablet_control import control_tablet


class TabletControlTests(unittest.TestCase):
    def reply(self, value):
        encoded = base64.b64encode(json.dumps(value).encode()).decode()
        return subprocess.CompletedProcess([], 0, f'Broadcast completed: result=-1, data="OPAD:{encoded}"')

    def test_live_show_and_hide_commands_confirm_tablet_state(self):
        for visible in (True, False):
            with patch("openpaddisplay.tablet_control.subprocess.run", return_value=self.reply({"visible": visible})) as run:
                self.assertEqual(control_tablet("metrics", visible=visible), {"visible": visible})
                args = run.call_args.args[0]
                self.assertEqual(args[:5], ["adb", "-d", "shell", "am", "broadcast"])
                self.assertEqual(args[-3:], ["--ez", "visible", str(visible).lower()])

    def test_missing_or_old_apk_is_an_error_not_a_silent_toggle(self):
        with patch("openpaddisplay.tablet_control.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "Broadcast completed: result=0")):
            with self.assertRaisesRegex(RuntimeError, "0.4.1"):
                control_tablet("metrics", visible=True)

    def test_usb_timeout_and_invalid_reply_are_reported(self):
        for result in (self.reply([]), self.reply({"visible": "false"})):
            with patch("openpaddisplay.tablet_control.subprocess.run", return_value=result):
                with self.assertRaisesRegex(RuntimeError, "inválida"):
                    control_tablet("status")
        with patch("openpaddisplay.tablet_control.subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 5)):
            with self.assertRaisesRegex(RuntimeError, "USB"):
                control_tablet("status")

    def test_guided_result_is_returned_to_computer_without_tablet_controls(self):
        expected = {"visible": False, "test_state": "completed", "test_result": "Sem limitação evidente"}
        with patch("openpaddisplay.tablet_control.subprocess.run", return_value=self.reply(expected)) as run:
            self.assertEqual(control_tablet("start_test", test_id="abc123", motion=True), expected)
            self.assertEqual(run.call_args.args[0][-6:], ["--es", "test_id", "abc123", "--ez", "motion", "true"])
