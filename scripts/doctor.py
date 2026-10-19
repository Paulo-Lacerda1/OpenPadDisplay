"""Read-only diagnostics; does not create a display or change the system."""
import os
from pathlib import Path
import shutil
import subprocess


def probe(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


print("Session:", os.environ.get("XDG_SESSION_TYPE", "unknown"))
print("Desktop:", os.environ.get("XDG_CURRENT_DESKTOP", "unknown"))
for tool in ("adb", "lsusb", "gst-inspect-1.0", "gdbus", "java"):
    print(f"{tool}: {shutil.which(tool) or 'MISSING'}")
try:
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    print(Gst.version_string())
    for name in ("videotestsrc", "videoconvert", "x264enc", "appsink", "pipewiresrc", "nvh264enc", "h264parse"):
        print(f"  {name}: {'available' if Gst.ElementFactory.find(name) else 'MISSING'}")
except (ImportError, ValueError) as exc:
    print("GStreamer Python bindings MISSING:", exc)
for command in (["adb", "devices", "-l"], ["lsusb", "-t"], ["gnome-shell", "--version"],
                ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]):
    code, output = probe(command)
    print(f"\n{' '.join(command)} (exit {code}):\n{output}")
code, output = probe(["gdbus", "introspect", "--session", "--dest", "org.gnome.Mutter.ScreenCast",
                      "--object-path", "/org/gnome/Mutter/ScreenCast"])
print("\nMutter ScreenCast D-Bus:", "available" if code == 0 else output)
print("This does not establish RecordVirtual refresh-rate support or measured 144 FPS.")
sdk_path = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
properties = Path(__file__).resolve().parents[1] / "android/local.properties"
if not sdk_path and properties.is_file():
    for line in properties.read_text().splitlines():
        if line.startswith("sdk.dir="):
            sdk_path = line.partition("=")[2].strip()
if not sdk_path and (Path.home() / "Android/Sdk").is_dir():
    sdk_path = str(Path.home() / "Android/Sdk")
print("\nAndroid SDK:", sdk_path or "not found; see docs/setup-pt.md")
if sdk_path:
    for component in ("platforms/android-35/android.jar", "build-tools/34.0.0/aapt2"):
        print(f"  {component}: {'available' if (Path(sdk_path) / component).is_file() else 'MISSING'}")
