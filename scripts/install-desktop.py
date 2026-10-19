#!/usr/bin/python3
"""Install the launcher and shared icon for the current desktop user."""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def desktop_quote(value):
    # Desktop Entry Exec values use their own quoting rules, not shell syntax.
    value = str(value).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    # Escape backslashes again for the Desktop Entry string-value layer.
    return ('"' + value + '"').replace("\\", "\\\\")


def install():
    if os.geteuid() == 0:
        raise SystemExit("Run this installer as your desktop user, without sudo.")
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    applications = data_home / "applications"
    icons = data_home / "icons/hicolor/512x512/apps"
    applications.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "assets/branding/openpaddisplay-512.png",
                    icons / "org.openpaddisplay.Host.png")
    launcher = applications / "org.openpaddisplay.Host.desktop"
    launcher.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=OpenPadDisplay\n"
        "Comment=Use your Android tablet as a USB display\n"
        "Comment[pt]=Usa o tablet como segundo monitor por USB\n"
        f"Exec={desktop_quote(ROOT / 'scripts/launch.sh')}\n"
        "Icon=org.openpaddisplay.Host\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "Keywords=tablet;display;monitor;USB;\n"
        "StartupNotify=true\n"
        "StartupWMClass=org.openpaddisplay.Host\n",
        encoding="utf-8",
    )
    for command in (("update-desktop-database", str(applications)),
                    ("gtk-update-icon-cache", "-f", "-t", str(data_home / "icons/hicolor"))):
        if shutil.which(command[0]):
            subprocess.run(command, check=False, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    print(f"Installed: {launcher}")
    print("Search for OpenPadDisplay in your application menu.")


if __name__ == "__main__":
    install()
