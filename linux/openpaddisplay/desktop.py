"""Small desktop controller for the existing USB streaming process."""
from collections import deque
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time

import gi

gi.require_foreign("cairo")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .layout import POSITIONS
from .preferences import load_position, save_position
from .tablet_control import control_tablet

ROOT = Path(__file__).resolve().parents[2]
RESOLUTION_PRESETS = (
    ("960x640", 960, 640),
    ("1440x960", 1440, 960),
    ("1920x1280", 1920, 1280),
)


def stream_command(root, resolution_id, fps, position=None, diagnostics=False,
                   source="virtual", pattern=None, duration=None):
    """Build the host command for a selected display mode."""
    resolutions = {preset_id: (width, height) for preset_id, width, height in RESOLUTION_PRESETS}
    width, height = resolutions[resolution_id]
    command = [
        str(root / "scripts/extend-usb.sh"),
        "--width", str(width), "--height", str(height), "--fps", str(fps),
        "--encoder", "auto", "--bitrate", "24000" if int(fps) > 60 else "12000",
    ]
    if source != "virtual":
        command.extend(("--source", source))
    if position is not None:
        command.extend(("--position", position))
    if pattern is not None:
        command.extend(("--pattern", pattern))
    if duration is not None:
        command.extend(("--duration", str(duration)))
    if diagnostics:
        command.append("--diagnostics")
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
        self.metrics_applied = False
        self.connected = False
        self.metrics_revision = 0
        self.test_cancel = None
        self.test_original_process = None
        self.test_transition = False
        self.test_process = None
        self.pending_test_result = None
        self.metrics_action = Gio.SimpleAction.new("metrics", GLib.VariantType.new("b"))
        self.metrics_action.connect("activate", lambda _action, value: self.diagnostics.set_active(value.get_boolean())
                                    if self.diagnostics.get_sensitive() else None)
        self.add_action(self.metrics_action)

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
        self.diagnostics = Gtk.ToggleButton(label="Mostrar métricas no tablet")
        self.diagnostics.set_tooltip_text("Mostra ou oculta as métricas sem interromper o vídeo. Requer APK 0.4.1+.")
        self.diagnostics.set_sensitive(False)
        self.diagnostics.connect("toggled", self.on_metrics_toggled)
        box.pack_start(self.diagnostics, False, False, 0)
        self.guided = Gtk.Button(label="Testar ligação (10 s)")
        self.guided.set_sensitive(False)
        self.guided.set_tooltip_text("Transmite barras de televisão em movimento durante 10 s e repõe o monitor. Requer APK 0.4.2+.")
        self.guided.connect("clicked", self.on_guided_test)
        box.pack_start(self.guided, False, False, 0)
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
                stream_command(ROOT, resolution_id, fps, self.position, diagnostics=True),
                cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, start_new_session=True,
            )
        except OSError as exc:
            self.status.set_text(f"Não foi possível iniciar: {exc}")
            return
        self.rate.set_sensitive(False)
        self.resolution.set_sensitive(False)
        self.diagnostics.set_sensitive(False)
        for button in self.position_buttons:
            button.set_sensitive(False)
        self.button.set_label("Desligar tablet")
        self.status.set_text("A ligar ao tablet…")
        threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()

    def read_output(self, process):
        with process.stdout:
            for line in process.stdout:
                GLib.idle_add(self.on_output, line.strip(), process)
        GLib.idle_add(self.on_finished, process, process.wait())

    def on_output(self, line, process=None):
        self.logs.append(line)
        self.log_view.get_buffer().set_text("\n".join(self.logs))
        if self.test_transition:
            if process is not None and process is self.test_process and line.startswith("Streaming with "):
                self.status.set_text("Teste em curso · barras RGB em movimento durante 10 s.")
            return GLib.SOURCE_REMOVE
        if process is not None and process is not self.process:
            return GLib.SOURCE_REMOVE
        if not self.stopping:
            if line.startswith("Streaming with "):
                self.connected = True
                self.status.set_text("Tablet ligado · Monitor estendido")
                self.sync_metrics()
                self.guided.set_sensitive(self.test_cancel is None)
                if self.pending_test_result is not None:
                    result = self.pending_test_result
                    self.pending_test_result = None
                    self.show_test_result(result)
            elif line.startswith("Session ended:"):
                self.connected = False
                self.metrics_revision += 1
                self.status.set_text("Ligação interrompida. A aguardar o tablet…")
                self.diagnostics.set_sensitive(True)
                self.guided.set_sensitive(False)
                self.cancel_guided_test()
        return GLib.SOURCE_REMOVE

    def on_metrics_toggled(self, _button):
        if self.process is not None and not self.stopping and self.diagnostics.get_sensitive():
            self.sync_metrics()

    def sync_metrics(self):
        process = self.process
        self.metrics_revision += 1
        revision = self.metrics_revision
        visible = self.diagnostics.get_active()
        self.diagnostics.set_sensitive(False)

        def worker():
            try:
                response = control_tablet("metrics", visible=visible)
                if response["visible"] != visible:
                    raise RuntimeError("O tablet não confirmou a alteração das métricas.")
                error = None
            except RuntimeError as exc:
                error = str(exc)
            GLib.idle_add(self.on_metrics_applied, process, revision, visible, error)

        threading.Thread(target=worker, daemon=True).start()

    def on_metrics_applied(self, process, revision, visible, error):
        if self.process is not process or self.stopping or revision != self.metrics_revision:
            return GLib.SOURCE_REMOVE
        if error:
            self.diagnostics.set_active(self.metrics_applied)
            self.status.set_text(error)
        else:
            self.metrics_applied = visible
            self.diagnostics.set_label("Ocultar métricas do tablet" if visible else "Mostrar métricas no tablet")
        self.diagnostics.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def on_guided_test(self, _button):
        if self.test_cancel is not None:
            self.cancel_guided_test()
            return
        if self.process is None or self.stopping or not self.connected:
            return
        self.start_guided_test()

    def start_guided_test(self):
        original = self.process
        resolution_id = self.resolution.get_active_id()
        fps = self.rate.get_active_id()
        original_command = stream_command(ROOT, resolution_id, fps, self.position, diagnostics=True)
        test_command = stream_command(ROOT, resolution_id, fps, diagnostics=True,
                                      source="test-pattern", pattern="scroll", duration=10)
        metrics_visible = self.diagnostics.get_active()
        cancelled = threading.Event()
        self.test_cancel = cancelled
        self.test_original_process = original
        self.test_transition = True
        self.connected = False
        self.metrics_revision += 1
        self.pending_test_result = None
        self.guided.set_label("Cancelar teste")
        self.guided.set_sensitive(True)
        self.diagnostics.set_sensitive(False)
        self.rate.set_sensitive(False)
        self.resolution.set_sensitive(False)
        for button in self.position_buttons:
            button.set_sensitive(False)
        self.status.set_text("A preparar o teste · barras de cor em movimento durante 10 s.")

        def worker():
            result = error = None
            safe_to_restore = True
            try:
                self.terminate_process(original)
                if cancelled.is_set():
                    return
                self.test_process = subprocess.Popen(
                    test_command, cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, start_new_session=True)
                summary = self.run_test_process(self.test_process, cancelled)
                if cancelled.is_set():
                    return
                self.test_process.wait(timeout=3)
                if self.test_process.returncode != 0:
                    raise RuntimeError("O teste de ligação falhou no host.")
                if not isinstance(summary, dict) or not summary.get("test_id") or summary.get("duration_seconds") != 10:
                    raise RuntimeError("O computador não confirmou os 10 segundos de teste.")
                response = control_tablet("status")
                deadline = time.monotonic() + 2
                while response.get("test_id") == summary["test_id"] and response.get("test_state") == "running":
                    if cancelled.wait(.1):
                        return
                    if time.monotonic() >= deadline:
                        break
                    response = control_tablet("status")
                if response.get("test_id") != summary["test_id"] or response.get("test_state") != "completed":
                    raise RuntimeError("O tablet não confirmou o resultado do teste.")
                result = response.get("test_result")
                if not isinstance(result, str) or not result:
                    raise RuntimeError("O tablet não devolveu as métricas do teste.")
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
                error = str(exc)
            finally:
                try:
                    self.terminate_process(self.test_process if self.test_process is not None else original)
                except (OSError, RuntimeError) as exc:
                    safe_to_restore = False
                    error = str(exc)
                self.test_process = None
                # Restore on the GTK thread: a late stop/close must win over recovery.
                GLib.idle_add(self.finish_guided_test, cancelled, result, error,
                              original_command if safe_to_restore else None, metrics_visible)

        threading.Thread(target=worker, daemon=True).start()

    def cancel_guided_test(self):
        if self.test_cancel is not None:
            self.test_cancel.set()
            if self.test_process is not None:
                self.send_signal(self.test_process, signal.SIGINT)

    @classmethod
    def terminate_process(cls, process):
        for sig, timeout in ((signal.SIGINT, 6), (signal.SIGTERM, 3), (signal.SIGKILL, 3)):
            cls.send_signal(process, sig)
            try:
                process.wait(timeout=timeout)
                return
            except subprocess.TimeoutExpired:
                continue
        raise RuntimeError("Não foi possível terminar o processo anterior; a ligação não foi reiniciada.")

    def run_test_process(self, process, cancelled):
        result = None
        lines = queue.Queue()

        def read_lines():
            try:
                with process.stdout:
                    for line in process.stdout:
                        lines.put(line)
            except (OSError, ValueError) as exc:
                lines.put(exc)
            finally:
                lines.put(None)

        threading.Thread(target=read_lines, daemon=True).start()
        deadline = time.monotonic() + 35
        while not cancelled.is_set():
            if time.monotonic() >= deadline:
                raise RuntimeError("O teste excedeu o tempo limite de 35 segundos.")
            try:
                line = lines.get(timeout=.25)
            except queue.Empty:
                continue
            if line is None:
                return result
            if isinstance(line, Exception):
                raise RuntimeError("Não foi possível ler o resultado do teste.") from line
            line = line.strip()
            if line.startswith("TEST_RESULT "):
                if result is not None:
                    raise ValueError("O host devolveu mais de um resultado de teste.")
                result = json.loads(line[len("TEST_RESULT "):])
                if not isinstance(result, dict):
                    raise ValueError("Resultado de teste inválido.")
            GLib.idle_add(self.on_output, line, process)
        return None

    def finish_guided_test(self, cancelled, result, error, original_command, metrics_visible):
        if self.test_cancel is not cancelled:
            return GLib.SOURCE_REMOVE
        self.test_cancel = None
        self.test_original_process = None
        self.test_transition = False
        self.pending_test_result = None
        self.process = None
        self.connected = False
        self.guided.set_label("Testar ligação (10 s)")
        self.guided.set_sensitive(False)
        self.diagnostics.set_sensitive(False)
        if not self.stopping and not self.closing and original_command is not None:
            try:
                self.process = subprocess.Popen(
                    original_command, cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, start_new_session=True)
            except OSError as exc:
                error = f"Não foi possível restaurar o monitor: {exc}"
        if self.process is not None:
            self.diagnostics.set_active(metrics_visible)
            self.button.set_sensitive(True)
            self.button.set_label("Desligar tablet")
            self.status.set_text("Teste cancelado · a restaurar o monitor…" if cancelled.is_set()
                                 else "Teste terminado · a restaurar o monitor…")
            if not cancelled.is_set():
                self.pending_test_result = f"Não foi possível concluir o teste: {error}" if error else result
            threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()
        else:
            self.stopping = False
            self.metrics_applied = False
            self.diagnostics.set_active(False)
            self.diagnostics.set_label("Mostrar métricas no tablet")
            self.rate.set_sensitive(True)
            self.resolution.set_sensitive(True)
            for button in self.position_buttons:
                button.set_sensitive(True)
            self.button.set_sensitive(True)
            self.button.set_label("Ligar tablet")
            self.hide_tablet_metrics()
            self.status.set_text(error or "Monitor desligado.")
            if self.closing:
                self.window.destroy()
                self.quit()
        return GLib.SOURCE_REMOVE

    def show_test_result(self, result):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                   message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.CLOSE,
                                   text="Resultado do teste da ligação")
        dialog.format_secondary_text(result)
        dialog.connect("response", lambda window, _response: window.destroy())
        dialog.show_all()

    def hide_tablet_metrics(self):
        def worker():
            try:
                control_tablet("metrics", visible=False)
            except RuntimeError:
                pass  # Disconnection must not be blocked by an unavailable USB device.
        threading.Thread(target=worker, daemon=True).start()

    def stop(self):
        if self.process is None or self.stopping:
            return
        self.stopping = True
        self.connected = False
        self.metrics_revision += 1
        self.cancel_guided_test()
        self.hide_tablet_metrics()
        self.diagnostics.set_sensitive(False)
        self.guided.set_sensitive(False)
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
        if self.test_transition and process is self.test_original_process:
            return GLib.SOURCE_REMOVE
        stopped = self.stopping
        self.pending_test_result = None
        self.process = None
        self.connected = False
        self.metrics_revision += 1
        self.stopping = False
        self.rate.set_sensitive(True)
        self.resolution.set_sensitive(True)
        self.diagnostics.set_sensitive(False)
        self.diagnostics.set_active(False)
        self.diagnostics.set_label("Mostrar métricas no tablet")
        self.metrics_applied = False
        self.cancel_guided_test()
        self.guided.set_sensitive(False)
        self.hide_tablet_metrics()
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
