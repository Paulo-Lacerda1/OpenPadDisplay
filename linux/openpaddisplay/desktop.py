"""Small desktop controller for the existing USB streaming process."""
from collections import deque
import os
from pathlib import Path
import signal
import subprocess
import threading

import gi

gi.require_foreign("cairo")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .layout import POSITIONS
from .preferences import load_position, save_position

ROOT = Path(__file__).resolve().parents[2]
RESOLUTION_PRESETS = (
    ("960x640", 960, 640),
    ("1440x960", 1440, 960),
    ("1920x1280", 1920, 1280),
)


def stream_command(root, resolution_id, fps, position=None):
    """Build the host command for a selected display mode."""
    resolutions = {preset_id: (width, height) for preset_id, width, height in RESOLUTION_PRESETS}
    width, height = resolutions[resolution_id]
    command = [
        str(root / "scripts/extend-usb.sh"),
        "--width", str(width), "--height", str(height), "--fps", str(fps),
        "--encoder", "auto", "--bitrate", "24000" if int(fps) > 60 else "12000",
    ]
    if position is not None:
        command.extend(("--position", position))
    return command


class PositionPreview(Gtk.DrawingArea):
    """A theme-aware schematic of the selected side of the desktop."""

    def __init__(self, position):
        super().__init__()
        self.position = position
        self.set_size_request(320, 138)
        self.get_accessible().set_name("Posição do tablet em relação aos monitores do computador")
        self.connect("draw", self.draw_layout)

    def draw_layout(self, _widget, cr):
        cr.translate((self.get_allocated_width() - 320) / 2, 0)
        arrangements = {
            "left": ((174, 37, 104, 62), (36, 41, 90, 56)),
            "right": ((36, 37, 104, 62), (188, 41, 90, 56)),
            "above": ((116, 77, 88, 48), (126, 4, 68, 44)),
            "below": ((116, 5, 88, 48), (126, 86, 68, 44)),
        }
        computer, tablet = arrangements[self.position]
        color = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)

        def screen(rect, label, selected=False):
            x, y, width, height = rect
            rgb = (.21, .52, .89) if selected else (color.red, color.green, color.blue)
            cr.set_source_rgba(*rgb, .16 if selected else .07)
            cr.rectangle(x, y, width, height)
            cr.fill_preserve()
            cr.set_source_rgba(*rgb, 1)
            cr.set_line_width(2)
            cr.stroke()
            cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
            cr.set_font_size(11)
            extents = cr.text_extents(label)
            cr.move_to(x + (width - extents[2]) / 2 - extents[0], y + height / 2 + 4)
            cr.show_text(label)

        # Dashed line represents the pointer's path between the two screens.
        cr.set_source_rgba(color.red, color.green, color.blue, .35)
        cr.set_line_width(1)
        cr.set_dash([3, 4])
        if self.position in ("left", "right"):
            start_x = computer[0] + (computer[2] if self.position == "right" else 0)
            end_x = tablet[0] + (tablet[2] if self.position == "left" else 0)
            cr.move_to(start_x, computer[1] + computer[3] / 2)
            cr.line_to(end_x, tablet[1] + tablet[3] / 2)
        else:
            start_y = computer[1] + (computer[3] if self.position == "below" else 0)
            end_y = tablet[1] + (tablet[3] if self.position == "above" else 0)
            cr.move_to(computer[0] + computer[2] / 2, start_y)
            cr.line_to(tablet[0] + tablet[2] / 2, end_y)
        cr.stroke()
        cr.set_dash([])
        screen(computer, "Computador")
        screen(tablet, "Tablet", True)
        x, y, width, height = computer
        cr.move_to(x + width / 2, y + height)
        cr.line_to(x + width / 2, y + height + 6)
        cr.move_to(x + width / 2 - 12, y + height + 6)
        cr.line_to(x + width / 2 + 12, y + height + 6)
        cr.stroke()
        return False


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
        self.position = load_position()
        self.position_buttons = []

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
        position_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        position_label = Gtk.Label(label="Posição do tablet", xalign=0)
        position_box.pack_start(position_label, False, False, 0)
        self.preview = PositionPreview(self.position)
        position_box.pack_start(self.preview, False, False, 0)
        choices = Gtk.Box(spacing=4, homogeneous=True)
        group = None
        for position, label in POSITIONS:
            button = Gtk.RadioButton.new_with_label_from_widget(group, label)
            if group is None:
                group = button
            button.set_mode(False)
            button.set_active(position == self.position)
            button.connect("toggled", self.on_position_changed, position)
            self.position_buttons.append(button)
            choices.pack_start(button, True, True, 0)
        position_box.pack_start(choices, False, False, 0)
        hint = Gtk.Label(label="Aplicada ao ligar · preferência guardada neste computador")
        hint.get_style_context().add_class("dim-label")
        hint.set_line_wrap(True)
        hint.set_max_width_chars(44)
        position_box.pack_start(hint, False, False, 0)
        box.pack_start(position_box, False, False, 0)
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

    def on_position_changed(self, button, position):
        if not button.get_active():
            return
        self.position = position
        self.preview.position = position
        self.preview.queue_draw()
        try:
            save_position(position)
        except OSError as exc:
            self.status.set_text(f"Posição selecionada, mas não foi possível guardar a preferência: {exc}")

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
                stream_command(ROOT, resolution_id, fps, self.position),
                cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, start_new_session=True,
            )
        except OSError as exc:
            self.status.set_text(f"Não foi possível iniciar: {exc}")
            return
        self.rate.set_sensitive(False)
        self.resolution.set_sensitive(False)
        for button in self.position_buttons:
            button.set_sensitive(False)
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
        for button in self.position_buttons:
            button.set_sensitive(True)
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
