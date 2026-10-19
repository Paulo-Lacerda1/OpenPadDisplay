"""Small per-user launcher preferences, stored atomically in XDG config."""

import json
import os
from pathlib import Path
import tempfile

from .layout import POSITIONS


def preferences_path():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "openpaddisplay/settings.json"


def load_position(path=None):
    try:
        data = json.loads((path or preferences_path()).read_text(encoding="utf-8"))
        position = data.get("position") if isinstance(data, dict) else None
        return position if position in dict(POSITIONS) else "right"
    except (OSError, ValueError):
        return "right"


def save_position(position, path=None):
    if position not in dict(POSITIONS):
        raise ValueError("Invalid tablet position")
    path = path or preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".settings-", delete=False) as output:
            temporary = Path(output.name)
            json.dump({"position": position}, output)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
