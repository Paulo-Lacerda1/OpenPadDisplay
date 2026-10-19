"""Small desktop controller for the existing USB streaming process."""
from collections import deque
import os
from pathlib import Path
import signal
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESOLUTION_PRESETS = (
    ("960x640", 960, 640),
    ("1440x960", 1440, 960),
    ("1920x1280", 1920, 1280),
)


def stream_command(root, resolution_id, fps):
    """Build the host command for a selected display mode."""
    resolutions = {preset_id: (width, height) for preset_id, width, height in RESOLUTION_PRESETS}
    width, height = resolutions[resolution_id]
    return [
        str(root / "scripts/extend-usb.sh"),
        "--width", str(width), "--height", str(height), "--fps", str(fps),
        "--encoder", "auto", "--bitrate", "24000" if int(fps) > 60 else "12000",
    ]


class DisplayApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.openpaddisplay.Host",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.process = None
        self.stopping = False
        self.closing = False
        self.logs = deque(maxlen=150)
        self.resolution = None

    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title="OpenPadDisplay")
        self.window.set_wmclass("org.openpaddisplay.Host", "org.openpaddisplay.Host")
        self.window.set_default_size(420, 390)
        self.window.set_resizable(False)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_icon_from_file(str(ROOT / "assets/branding/openpaddisplay-512.png"))
        self.window.connect("delete-event", self.on_close)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin=28)
        self.window.add(box)
        from gi.repository import GdkPixbuf
        image = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(ROOT / "assets/branding/openpaddisplay-512.png"), 88, 88, True))
        box.pack_start(image, False, False, 0)
        title = Gtk.Label()
        title.set_markup('<span size="x-large" weight="bold">OpenPadDisplay</span>')
        box.pack_start(title, False, False, 0)
        subtitle = Gtk.Label(label="O teu tablet, um segundo monitor.")
        box.pack_start(subtitle, False, False, 0)
        self.status = Gtk.Label(label="Liga o tablet por USB para começar.")
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(44)
        box.pack_start(self.status, False, False, 0)
        row = Gtk.Box(spacing=12)
        row.pack_start(Gtk.Label(label="Resolução"), False, False, 0)
        self.resolution = Gtk.ComboBoxText()
        for preset_id, width, height in RESOLUTION_PRESETS:
            self.resolution.append(preset_id, f"{width} × {height}")
        self.resolution.set_active_id("1920x1280")
        row.pack_end(self.resolution, False, False, 0)
        box.pack_start(row, False, False, 0)
        row = Gtk.Box(spacing=12)
        row.pack_start(Gtk.Label(label="Frequência"), False, False, 0)
        self.rate = Gtk.ComboBoxText()
        for fps in (60, 120, 144):
            self.rate.append(str(fps), f"{fps} Hz")
        self.rate.set_active_id("60")
        row.pack_end(self.rate, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.button = Gtk.Button(label="Ligar tablet")
        self.button.get_style_context().add_class("suggested-action")
        self.button.connect("clicked", self.on_toggle)
        box.pack_start(self.button, False, False, 0)
        details = Gtk.Expander(label="Detalhes da ligação")
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(-1, 160)
        self.log_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll.add(self.log_view)
        details.add(scroll)
        box.pack_start(details, True, True, 0)
        self.window.show_all()

    def on_toggle(self, _button):
        if self.process is not None:
            self.stop()
            return
        self.logs.clear()
        self.log_view.get_buffer().set_text("")
        fps = self.rate.get_active_id()
        resolution_id = self.resolution.get_active_id()
        try:
            self.process = subprocess.Popen(
                stream_command(ROOT, resolution_id, fps),
                cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, start_new_session=True,
            )
        except OSError as exc:
            self.status.set_text(f"Não foi possível iniciar: {exc}")
            return
        self.rate.set_sensitive(False)
        self.resolution.set_sensitive(False)
        self.button.set_label("Desligar tablet")
        self.status.set_text("A ligar ao tablet…")
        threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()

    def read_output(self, process):
        with process.stdout:
            for line in process.stdout:
                GLib.idle_add(self.on_output, line.strip())
        GLib.idle_add(self.on_finished, process, process.wait())

    def on_output(self, line):
        self.logs.append(line)
        self.log_view.get_buffer().set_text("\n".join(self.logs))
        if not self.stopping:
            if line.startswith("Streaming with "):
                self.status.set_text("Tablet ligado · Monitor estendido")
            elif line.startswith("Session ended:"):
                self.status.set_text("Ligação interrompida. A aguardar o tablet…")
        return GLib.SOURCE_REMOVE

    def stop(self):
        if self.process is None or self.stopping:
            return
        self.stopping = True
        self.button.set_sensitive(False)
        self.status.set_text("A desligar o monitor…")
        self.send_signal(self.process, signal.SIGINT)
        GLib.timeout_add_seconds(6, self.escalate_stop, self.process)

    @staticmethod
    def send_signal(process, sig):
        if process.poll() is None:
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass

    def escalate_stop(self, process):
        self.send_signal(process, signal.SIGTERM)
        GLib.timeout_add_seconds(3, self.force_stop, process)
        return GLib.SOURCE_REMOVE

    def force_stop(self, process):
        self.send_signal(process, signal.SIGKILL)
        return GLib.SOURCE_REMOVE

    def on_finished(self, process, code):
        if self.process is not process:
            return GLib.SOURCE_REMOVE
        stopped = self.stopping
        self.process = None
        self.stopping = False
        self.rate.set_sensitive(True)
        self.resolution.set_sensitive(True)
        self.button.set_sensitive(True)
        self.button.set_label("Ligar tablet")
        if stopped or code == 0:
            self.status.set_text("Monitor desligado. Podes voltar a ligar.")
        else:
            if any("Address already in use" in line for line in self.logs):
                self.status.set_text("Já existe um servidor em execução. Termina-o antes de ligar aqui.")
            else:
                self.status.set_text("Não foi possível ligar. Confirma o cabo USB e a autorização "
                                     "no tablet. Consulta os detalhes abaixo.")
        if self.closing:
            self.window.destroy()
            self.quit()
        return GLib.SOURCE_REMOVE

    def on_close(self, _window, _event):
        if self.process is not None:
            self.closing = True
            self.stop()
            return True
        return False


def main():
    return DisplayApplication().run(None)


if __name__ == "__main__":
    raise SystemExit(main())
