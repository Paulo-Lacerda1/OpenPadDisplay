import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpaddisplay.preferences import load_position, save_position


class PreferenceTests(unittest.TestCase):
    def test_saved_position_survives_reload_and_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested/settings.json"
            self.assertEqual(load_position(path), "right")
            for position in ("left", "above", "below", "right"):
                save_position(position, path)
                self.assertEqual(load_position(path), position)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_corrupt_or_unknown_preferences_use_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for content in ("broken", "[]", '{"position":"diagonal"}', '{}'):
                path.write_text(content)
                self.assertEqual(load_position(path), "right")

    def test_failed_atomic_write_preserves_existing_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_position("left", path)
            with patch("openpaddisplay.preferences.os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    save_position("above", path)
            self.assertEqual(load_position(path), "left")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_xdg_config_and_invalid_position(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"XDG_CONFIG_HOME": directory}):
            save_position("above")
            self.assertEqual(load_position(), "above")
            path = Path(directory) / "openpaddisplay/settings.json"
            self.assertEqual(json.loads(path.read_text()), {"position": "above"})
            with self.assertRaises(ValueError):
                save_position("diagonal")
