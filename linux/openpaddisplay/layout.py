"""Plan temporary Mutter monitor layouts without changing existing modes."""

import math
import time

POSITIONS = (("left", "À esquerda"), ("right", "À direita"),
             ("above", "Acima"), ("below", "Abaixo"))
DISPLAY_BUS = "org.gnome.Mutter.DisplayConfig"
DISPLAY_PATH = "/org/gnome/Mutter/DisplayConfig"


class LayoutError(ValueError):
    """The requested placement cannot safely be applied."""


def current_mode(monitor):
    modes = [mode for mode in monitor[1] if mode[6].get("is-current")]
    if len(modes) != 1:
        raise LayoutError(f"Cannot identify the active mode for {monitor[0][0]}")
    return modes[0]


def configuration_rows(state):
    by_spec = {tuple(monitor[0]): monitor for monitor in state[1]}
    rows = []
    for x, y, scale, transform, primary, specs, _ in state[2]:
        members = []
        for spec in specs:
            monitor = by_spec[tuple(spec)]
            properties = {}
            if "is-underscanning" in monitor[2]:
                properties["enable_underscanning"] = monitor[2]["is-underscanning"]
            members.append((spec[0], current_mode(monitor)[0], properties))
        rows.append([x, y, scale, transform, primary, members])
    return rows


def snapshot_state(current, desired):
    """Use a snapshot's arrangement and active modes with a fresh serial.

    Refuse to replay a snapshot if an output was connected/disconnected or a
    saved mode is no longer available while the virtual monitor was starting.
    """
    if {tuple(m[0]) for m in current[1]} != {tuple(m[0]) for m in desired[1]}:
        raise LayoutError("Connected monitors changed; keeping the current desktop layout")
    wanted_modes = {tuple(m[0]): current_mode(m)[0] for m in desired[1]
                    if any(mode[6].get("is-current") for mode in m[1])}
    monitors = []
    for spec, modes, properties in current[1]:
        wanted = wanted_modes.get(tuple(spec))
        if wanted is not None and not any(mode[0] == wanted for mode in modes):
            raise LayoutError(f"The saved display mode for {spec[0]} is no longer available")
        adjusted_modes = [(*mode[:6], {**mode[6], "is-current": mode[0] == wanted}) for mode in modes]
        monitors.append((spec, adjusted_modes, properties))
    return current[0], monitors, desired[2], {**current[3], "layout-mode": desired[3].get("layout-mode", 1)}


def layout_signature(state):
    modes = tuple(sorted((tuple(m[0]), mode[0]) for m in state[1]
                         for mode in m[1] if mode[6].get("is-current")))
    logical = tuple(sorted((*row[:5], tuple(sorted(tuple(spec) for spec in row[5]))) for row in state[2]))
    return modes, logical, state[3].get("layout-mode", 1)


def positioned_layout(state, connector, position):
    """Return ApplyMonitorsConfig rows, preserving other displays as a group.

    Coordinates use Mutter's logical or physical layout units, including scale
    and rotation. Choose a monitor on the requested outside edge as an anchor
    so the new output always shares a usable edge with the existing desktop.
    """
    if position not in dict(POSITIONS):
        raise LayoutError(f"Unknown tablet position: {position}")
    _, monitors, logical, properties = state
    by_spec = {tuple(monitor[0]): monitor for monitor in monitors}
    rows = []
    bounds = []
    target = None
    for logical_monitor in logical:
        x, y, scale, transform, primary, specs, _ = logical_monitor
        members = []
        for spec in specs:
            monitor = by_spec[tuple(spec)]
            mode = current_mode(monitor)
            member_properties = {}
            if "is-underscanning" in monitor[2]:
                member_properties["enable_underscanning"] = monitor[2]["is-underscanning"]
            members.append((spec[0], mode[0], member_properties))
        if not members:
            raise LayoutError("An active logical monitor has no outputs")
        mode = current_mode(by_spec[tuple(specs[0])])
        width, height = mode[1:3]
        if transform % 2:
            width, height = height, width
        if properties.get("layout-mode", 1) == 1:
            width, height = width / scale, height / scale
        width, height = int(math.floor(width + .5)), int(math.floor(height + .5))
        if width <= 0 or height <= 0:
            raise LayoutError("Invalid logical monitor dimensions")
        row = [x, y, scale, transform, primary, members]
        if any(spec[0] == connector for spec in specs):
            if len(specs) != 1 or target is not None:
                raise LayoutError("Tablet must have its own logical monitor")
            target = (row, width, height)
        else:
            bounds.append((x, y, width, height, primary))
        rows.append(row)
    if target is None or not bounds:
        raise LayoutError("Tablet and an existing desktop must both be active")
    row, width, height = target
    # Prefer the primary display when multiple monitors share an outside edge.
    if position == "right":
        anchor = max(bounds, key=lambda b: (b[0] + b[2], b[4], -b[1]))
        row[0], row[1] = anchor[0] + anchor[2], anchor[1]
    elif position == "left":
        anchor = min(bounds, key=lambda b: (b[0], not b[4], b[1]))
        row[0], row[1] = anchor[0] - width, anchor[1]
    elif position == "above":
        anchor = min(bounds, key=lambda b: (b[1], not b[4], b[0]))
        row[0], row[1] = anchor[0], anchor[1] - height
    else:
        anchor = max(bounds, key=lambda b: (b[1] + b[3], b[4], -b[0]))
        row[0], row[1] = anchor[0], anchor[1] + anchor[3]
    # Mutter requires a nonnegative desktop whose origin is occupied.
    min_x = min(item[0] for item in rows)
    min_y = min(item[1] for item in rows)
    for item in rows:
        item[0] -= min_x
        item[1] -= min_y
    return rows


class MonitorLayout:
    def __init__(self, connection):
        from gi.repository import Gio, GLib
        self.connection = connection
        self.Gio, self.GLib = Gio, GLib

    def state(self):
        try:
            return self.connection.call_sync(
                DISPLAY_BUS, DISPLAY_PATH, DISPLAY_BUS, "GetCurrentState", None,
                None, self.Gio.DBusCallFlags.NONE, 5000, None,
            ).unpack()
        except self.GLib.Error as exc:
            raise LayoutError(f"Could not read the desktop layout: {exc.message}") from exc

    def place(self, before, position):
        """Place a new output around the desktop captured before its creation."""
        existing_specs = {tuple(monitor[0]) for monitor in before[1]}
        for attempt in range(3):
            state = self.state()
            candidates = [monitor[0][0] for monitor in state[1]
                          if tuple(monitor[0]) not in existing_specs
                          and monitor[0][0].startswith("Meta-")]
            if len(candidates) != 1:
                raise LayoutError("Cannot uniquely identify this session's virtual monitor")
            connector = candidates[0]
            new_monitors = [monitor for monitor in state[1] if monitor[0][0] == connector]
            new_logical = [row for row in state[2] if any(spec[0] == connector for spec in row[5])]
            desired = (state[0], [*before[1], *new_monitors], [*before[2], *new_logical], before[3])
            state = snapshot_state(state, desired)
            rows = positioned_layout(state, connector, position)
            try:
                self.apply(state, rows)
                return connector
            except self.GLib.Error as exc:
                # A monitor hotplug can invalidate the serial between calls.
                if attempt == 2 or self.Gio.DBusError.get_remote_error(exc) != "org.freedesktop.DBus.Error.AccessDenied":
                    raise LayoutError(f"Could not position the tablet: {exc.message}") from exc

    def apply(self, state, rows):
        # Rebuild variants explicitly; unpack() returns ordinary Python data.
        rows = [(*row[:5], [(name, mode, {key: self.GLib.Variant("b", value)
                                        for key, value in props.items()})
                           for name, mode, props in row[5]]) for row in rows]
        properties = {}
        if state[3].get("supports-changing-layout-mode"):
            properties["layout-mode"] = self.GLib.Variant("u", state[3]["layout-mode"])
        self.connection.call_sync(
            DISPLAY_BUS, DISPLAY_PATH, DISPLAY_BUS, "ApplyMonitorsConfig",
            self.GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (state[0], 1, rows, properties)),
            None, self.Gio.DBusCallFlags.NONE, 5000, None,
        )

    def restore(self, before, connector):
        deadline = time.monotonic() + 3
        while True:
            current = self.state()
            if not any(monitor[0][0] == connector for monitor in current[1]):
                break
            if time.monotonic() >= deadline:
                raise LayoutError("Virtual monitor did not disappear before layout restoration")
            time.sleep(.05)
        for attempt in range(3):
            desired = snapshot_state(self.state(), before)
            try:
                self.apply(desired, configuration_rows(desired))
                return
            except self.GLib.Error as exc:
                if attempt == 2 or self.Gio.DBusError.get_remote_error(exc) != "org.freedesktop.DBus.Error.AccessDenied":
                    raise LayoutError(f"Could not restore the desktop layout: {exc.message}") from exc

