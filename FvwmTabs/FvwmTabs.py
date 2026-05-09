#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import atexit
import fnmatch
import logging
from logging.handlers import RotatingFileHandler
import os
import queue
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
tk = None
simpledialog = None

# Runtime paths and timing knobs. Keep these near the top so packagers and FVWM
# users can see what the process writes under ~/.fvwm.
LOG_PATH = os.path.expanduser("~/.fvwm/fvwmtabs.log")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "FvwmTabs.conf")
VERSION_LABEL = "FvwmTabs v12-stable"
DEFAULT_GEOMETRY = "170x40"
TABBER_WINDOW_CLASS = "FvwmTabs"
TABBER_RESOURCE_PREFIX = "fvwmTabs"
KEEPALIVE_MS = 1000
WATCH_INTERVAL = 0.15
AUTOSWALLOW_RETRY_MS = 250
AUTOSWALLOW_RETRIES = 8
AUTOSWALLOW_CACHE_TTL = 300
AUTOSWALLOW_FALLBACK_SCAN_MS = 5000
AUTOSWALLOW_SUPPRESS_TTL = 60
LOG_THROTTLE_SECONDS = 30
CLIENT_LIST_PROPERTIES = ("_NET_CLIENT_LIST", "_NET_CLIENT_LIST_STACKING")

# Tk color sets. The UI is intentionally small and toolkit-native; keep theme
# edits conservative so existing FVWM desktops do not get a surprise redesign.
THEMES = {
    "black": {
        "tabbar_bg": "#222222",
        "content_bg": "#111111",
        "button_bg": "#333333",
        "button_fg": "#eeeeee",
        "button_active_bg": "#444444",
        "button_active_fg": "#ffffff",
        "button_selected_bg": "#4a4a4a",
        "button_selected_fg": "#ffffff",
        "button_selected_border": "#7aa7ff",
        "close_fg": "#bbbbbb",
        "menu_bg": "#202020",
        "menu_fg": "#f0f0f0",
        "menu_active_bg": "#4a4a4a",
        "menu_active_fg": "#ffffff",
    },
    "white": {
        "tabbar_bg": "#e8e8e8",
        "content_bg": "#f7f7f7",
        "button_bg": "#ffffff",
        "button_fg": "#111111",
        "button_active_bg": "#dcdcdc",
        "button_active_fg": "#000000",
        "button_selected_bg": "#d9eaff",
        "button_selected_fg": "#000000",
        "button_selected_border": "#2f6fbd",
        "close_fg": "#444444",
        "menu_bg": "#ffffff",
        "menu_fg": "#111111",
        "menu_active_bg": "#d9d9d9",
        "menu_active_fg": "#000000",
    },
}

_ROOT_WIN_ID = None
_LOGGER = None
_LAST_EXTERNAL_FAILURE_LOG = {}
_LAST_CLIENT_LIST_UNAVAILABLE_LOG = 0.0


def _session_suffix():
    display = os.environ.get("DISPLAY", ":0")
    safe_display = display.replace(":", "").replace(".", "_")
    safe_display = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in safe_display)
    return safe_display or "0"


SOCKET_PATH = os.path.expanduser(f"~/.fvwm/.fvwmtabs-{_session_suffix()}.sock")
PID_PATH = os.path.expanduser(f"~/.fvwm/.fvwmtabs-{_session_suffix()}.pid")


# Logging helpers

def _setup_logging(debug=False):
    global _LOGGER
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    logger = logging.getLogger("FvwmTabs")
    logger.handlers[:] = []
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=512 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    _LOGGER = logger
    return logger


def _log(level, message, *args):
    if _LOGGER is not None:
        _LOGGER.log(level, message, *args)


def _log_external_failure(cmd, level, message, *args):
    key = tuple(map(str, cmd))
    now = time.monotonic()
    last = _LAST_EXTERNAL_FAILURE_LOG.get(key)
    if last is not None and now - last < LOG_THROTTLE_SECONDS:
        return
    _LAST_EXTERNAL_FAILURE_LOG[key] = now
    _log(level, message, *args)


def _run_capture(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        _log_external_failure(cmd, logging.ERROR, "external command not found: %s", cmd[0])
        raise
    except subprocess.CalledProcessError as err:
        output = (err.output or "").strip()
        _log_external_failure(
            cmd,
            logging.WARNING,
            "external command failed rc=%s cmd=%r output=%r",
            err.returncode,
            cmd,
            output,
        )
        raise


def _run_quiet(cmd):
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            _log_external_failure(
                cmd,
                logging.WARNING,
                "external command failed rc=%s cmd=%r output=%r",
                result.returncode,
                cmd,
                (result.stdout or "").strip(),
            )
        return result.returncode == 0
    except FileNotFoundError:
        _log_external_failure(cmd, logging.ERROR, "external command not found: %s", cmd[0])
    except Exception as err:
        _log_external_failure(cmd, logging.WARNING, "external command error cmd=%r error=%s", cmd, err)
    return False


def _xdo(*args):
    return _run_quiet(["xdotool", *map(str, args)])


# Configuration parsing

def _normalize_tabber_id(value, default=None):
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    if text.lower() == "default":
        return 1
    try:
        tabber_id = int(text)
    except Exception:
        return default
    if tabber_id <= 0:
        return default
    return tabber_id


def _import_tkinter():
    global tk, simpledialog
    if tk is not None and simpledialog is not None:
        return True
    try:
        import tkinter as tk_module
        from tkinter import simpledialog as simpledialog_module
    except ImportError as err:
        _log(logging.ERROR, "Tkinter is required but could not be imported: %s", err)
        print(f"FvwmTabs: Tkinter is required but could not be imported: {err}", file=sys.stderr)
        return False
    tk = tk_module
    simpledialog = simpledialog_module
    return True


def _parse_rule_list(value):
    rules = []
    for chunk in value.split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            pattern, tabber_id = item.rsplit(None, 1)
        except ValueError:
            _log(logging.WARNING, "Invalid autoSwallow rule ignored: %s", item)
            continue
        if not pattern.strip():
            _log(logging.WARNING, "Invalid autoSwallow rule ignored: %s", item)
            continue
        normalized_id = _normalize_tabber_id(tabber_id)
        if normalized_id is None:
            _log(logging.WARNING, "Invalid autoSwallow rule ignored: %s", item)
            continue
        rules.append((pattern.strip(), normalized_id))
    return rules


def _load_config(path):
    config = {
        "theme": "black",
        "debug": False,
        "auto_swallow_on_startup": False,
        "auto_swallow_class": [],
        "auto_swallow_resource": [],
        "auto_swallow_name": [],
        "unknown_keys": [],
    }
    if not os.path.exists(path):
        return config

    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.split("#", 1)[0].strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key == "theme":
                    theme = value.lower()
                    if theme in THEMES:
                        config["theme"] = theme
                elif key == "debug":
                    config["debug"] = _parse_bool(value)
                elif key == "autoSwallowOnStartup":
                    config["auto_swallow_on_startup"] = _parse_bool(value)
                elif key == "autoSwallowClass":
                    config["auto_swallow_class"].extend(_parse_rule_list(value))
                elif key == "autoSwallowResource":
                    # Compatibility rule: this matches the first WM_CLASS
                    # string, also called instance/resource by X11 tools.
                    config["auto_swallow_resource"].extend(_parse_rule_list(value))
                elif key == "autoSwallowName":
                    config["auto_swallow_name"].extend(_parse_rule_list(value))
                else:
                    config["unknown_keys"].append(key)
    except Exception as err:
        _log(logging.WARNING, "failed to load config %s: %s", path, err)
    return config


def _parse_bool(value):
    return str(value).strip().lower() in {"1", "yes", "true", "on", "enable", "enabled"}


# External X11 helpers

def _get_root_window_id():
    global _ROOT_WIN_ID
    if _ROOT_WIN_ID is not None:
        return _ROOT_WIN_ID
    try:
        out = _run_capture(["xwininfo", "-root"])
        for line in out.splitlines():
            if "Window id:" not in line:
                continue
            for token in line.split():
                if token.startswith("0x"):
                    _ROOT_WIN_ID = int(token, 16)
                    return _ROOT_WIN_ID
    except Exception:
        return None
    return None


def _get_window_geometry(win_id):
    try:
        out = _run_capture(["xdotool", "getwindowgeometry", "--shell", str(win_id)])
        data = {}
        for line in out.splitlines():
            if "=" in line:
                key, value = line.strip().split("=", 1)
                data[key] = value
        width = int(data.get("WIDTH", "0")) or None
        height = int(data.get("HEIGHT", "0")) or None
        return width, height
    except Exception:
        return None, None


def _xprop_key(raw):
    head = raw.split("=", 1)[0].split(":", 1)[0].strip()
    return head.split("(", 1)[0].strip()


def _parse_xprop_text(raw):
    if "=" not in raw:
        return ""
    value = raw.split("=", 1)[1].strip()
    if value.lower() == "not found.":
        return ""
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value.strip().strip('"')


def _parse_wm_class(raw):
    if "=" not in raw:
        return "", ""
    raw = raw.split("=", 1)[1].strip()
    parts = [part.strip().strip('"') for part in raw.split(",") if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], parts[0]
    return "", ""


def _parse_xprop_window(raw):
    lowered = raw.lower()
    if "not found" in lowered or "no such atom" in lowered:
        return None
    for token in raw.replace(",", " ").split():
        if token.startswith("0x"):
            return token
    return None


# X11 identity parsing

def _get_window_identity(win_id):
    identity = {
        "id": win_id,
        "resource": "",
        "class": "",
        "name": "",
        "net_name": "",
        "wm_name": "",
        "transient_for": None,
        "role": None,
        "window_type": "",
    }
    try:
        out = _run_capture([
            "xprop",
            "-id",
            str(win_id),
            "WM_CLASS",
            "WM_NAME",
            "_NET_WM_NAME",
            "WM_TRANSIENT_FOR",
            "WM_WINDOW_ROLE",
            "_NET_WM_WINDOW_TYPE",
        ])
    except Exception:
        out = ""

    for line in out.splitlines():
        stripped = line.strip()
        key = _xprop_key(stripped)
        if key == "WM_CLASS":
            identity["resource"], identity["class"] = _parse_wm_class(stripped)
        elif key == "_NET_WM_NAME":
            identity["net_name"] = _parse_xprop_text(stripped)
        elif key == "WM_NAME":
            identity["wm_name"] = _parse_xprop_text(stripped)
        elif key == "WM_TRANSIENT_FOR":
            identity["transient_for"] = _parse_xprop_window(stripped)
        elif key == "WM_WINDOW_ROLE":
            identity["role"] = _parse_xprop_text(stripped)
        elif key == "_NET_WM_WINDOW_TYPE":
            identity["window_type"] = stripped.split("=", 1)[1].strip() if "=" in stripped else ""

    identity["name"] = identity["net_name"] or identity["wm_name"]
    if not identity["name"]:
        try:
            identity["name"] = _run_capture(["xdotool", "getwindowname", str(win_id)]).strip()
        except Exception:
            identity["name"] = ""

    return identity


def _format_identity(identity):
    return (
        "id=0x{0:x} resource={1!r} class={2!r} name={3!r} "
        "net_name={4!r} wm_name={5!r} transient_for={6!r} role={7!r}"
    ).format(
        identity.get("id", 0),
        identity.get("resource", ""),
        identity.get("class", ""),
        identity.get("name", ""),
        identity.get("net_name", ""),
        identity.get("wm_name", ""),
        identity.get("transient_for"),
        identity.get("role"),
    )


def _matches_pattern(pattern, value):
    if not pattern or not value:
        return False
    return fnmatch.fnmatch(value.lower(), pattern.lower())


def _window_exists(win_id):
    try:
        _run_capture(["xdotool", "getwindowname", str(win_id)])
        return True
    except Exception:
        return False


def _select_window():
    # xdotool/X11 chooses the cursor shown here; there is no reliable plain
    # "+" cursor option to set from this script.
    try:
        raw = _run_capture(["xdotool", "selectwindow"]).strip()
        return int(raw, 0)
    except Exception:
        return None


def _extract_window_ids(raw):
    windows = set()
    for token in raw.replace(",", " ").split():
        token = token.strip().rstrip(".,;")
        if not token.startswith("0x"):
            continue
        try:
            win_id = int(token, 16)
        except Exception:
            continue
        if win_id:
            windows.add(win_id)
    return windows


def _log_client_list_unavailable():
    global _LAST_CLIENT_LIST_UNAVAILABLE_LOG
    now = time.monotonic()
    if now - _LAST_CLIENT_LIST_UNAVAILABLE_LOG < LOG_THROTTLE_SECONDS:
        return
    _LAST_CLIENT_LIST_UNAVAILABLE_LOG = now
    _log(
        logging.WARNING,
        "autoSwallow cannot read client windows: neither _NET_CLIENT_LIST nor "
        "_NET_CLIENT_LIST_STACKING is available",
    )


def _get_client_window_snapshot():
    details = {
        prop: {"available": False, "windows": set(), "raw": ""}
        for prop in CLIENT_LIST_PROPERTIES
    }
    try:
        out = _run_capture(["xprop", "-root", *CLIENT_LIST_PROPERTIES])
    except Exception:
        chunks = []
        for prop in CLIENT_LIST_PROPERTIES:
            try:
                chunks.append(_run_capture(["xprop", "-root", prop]))
            except Exception:
                pass
        if not chunks:
            _log_client_list_unavailable()
            return set(), details
        out = "\n".join(chunks)

    for line in out.splitlines():
        stripped = line.strip()
        key = _xprop_key(stripped)
        if key not in details:
            continue
        if details[key]["raw"]:
            details[key]["raw"] += "\n" + stripped
        else:
            details[key]["raw"] = stripped

    windows = set()
    for prop, prop_details in details.items():
        raw = prop_details["raw"]
        lowered = raw.lower()
        if not raw or "not found" in lowered or "no such atom" in lowered:
            continue
        prop_details["available"] = True
        prop_details["windows"] = _extract_window_ids(raw)
        windows.update(prop_details["windows"])

    if not any(prop_details["available"] for prop_details in details.values()):
        _log_client_list_unavailable()

    return windows, details


def _list_client_windows():
    windows, _details = _get_client_window_snapshot()
    return windows


# WindowWatcher turns root-window client-list changes into Tk-thread queue
# events. All reparenting still happens on the Tk/server thread.
class WindowWatcher(threading.Thread):
    def __init__(self, out_queue, stop_event, interval=WATCH_INTERVAL):
        super().__init__(daemon=True)
        self.out_queue = out_queue
        self.stop_event = stop_event
        self.interval = interval
        self.known = _list_client_windows()

    def run(self):
        while not self.stop_event.is_set():
            current = _list_client_windows()
            new_windows = current - self.known
            removed_windows = self.known - current
            if new_windows or removed_windows:
                self.out_queue.put(("watch_windows", (current, new_windows, removed_windows)))
            self.known = current
            self.stop_event.wait(self.interval)


class Tab:
    """Bookkeeping for one client window inside a tabber."""

    def __init__(self, win_id, title, frame, button, close_button, width=None, height=None):
        self.win_id = win_id
        self.title = title
        self.frame = frame
        self.button = button
        self.close_button = close_button
        self.width = width
        self.height = height


class Tabber:
    """Small Tk shell that owns the tab UI and the X11 tab lifecycle."""

    def __init__(
        self,
        root,
        tabber_id,
        theme_name="black",
        geometry=None,
        on_destroy=None,
        on_active=None,
        on_window_released=None,
        request_new_tabber=None,
        request_add_loop=None,
        request_command=None,
    ):
        self.root = root
        self.tabber_id = tabber_id
        self.on_destroy = on_destroy
        self.on_active = on_active
        self.on_window_released = on_window_released
        self.request_new_tabber = request_new_tabber
        self.request_add_loop = request_add_loop
        self.request_command = request_command
        self.tabs = []
        self.current = None
        self.theme_name = theme_name if theme_name in THEMES else "black"
        self._keepalive_job = None
        self._menu_visible = False

        self.resource_name = f"{TABBER_RESOURCE_PREFIX}{tabber_id}"
        self.window_title = f"{TABBER_WINDOW_CLASS} [{tabber_id}]"
        self.top = tk.Toplevel(root, name=self.resource_name, class_=TABBER_WINDOW_CLASS)
        self.top.title(self.window_title)
        self.top.geometry(geometry or DEFAULT_GEOMETRY)

        self.tabbar = tk.Frame(self.top, highlightthickness=0, bd=0)
        self.tabbar.pack(side="top", fill="x")

        self.menu_button = tk.Button(
            self.tabbar,
            text="v",
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            command=self._toggle_dropdown,
        )
        self.menu_button.pack(side="right", padx=2, pady=2)

        self.tabs_holder = tk.Frame(self.tabbar, highlightthickness=0, bd=0)
        self.tabs_holder.pack(side="left", fill="x", expand=True)

        self.content = tk.Frame(self.top, highlightthickness=0, bd=0)
        self.content.pack(side="top", fill="both", expand=True)
        self.content.bind("<Configure>", self._on_resize)

        self._dropdown = tk.Menu(self.top, tearoff=0)
        self._dropdown.bind("<Unmap>", self._on_menu_unmap, add="+")
        self._dropdown.bind("<ButtonRelease-1>", self._on_menu_click, add="+")

        self.top.protocol("WM_DELETE_WINDOW", self.destroy)
        self.top.bind("<ButtonPress-1>", self._dismiss_menu, add="+")
        self.top.bind("<FocusIn>", self._on_focus_in, add="+")
        self.root.bind_all("<ButtonPress>", self._on_global_button_press, add="+")

        self._apply_theme()
        self._schedule_keepalive()

    def _configure_menu_widget(self, menu):
        theme = THEMES[self.theme_name]
        menu.configure(
            bg=theme["menu_bg"],
            fg=theme["menu_fg"],
            activebackground=theme["menu_active_bg"],
            activeforeground=theme["menu_active_fg"],
            bd=1,
            relief="flat",
        )

    def _apply_theme(self):
        theme = THEMES[self.theme_name]
        self.top.configure(bg=theme["tabbar_bg"])
        self.tabbar.configure(bg=theme["tabbar_bg"])
        self.tabs_holder.configure(bg=theme["tabbar_bg"])
        self.content.configure(bg=theme["content_bg"])
        self._configure_menu_widget(self._dropdown)
        self.menu_button.configure(
            bg=theme["button_bg"],
            fg=theme["button_fg"],
            activebackground=theme["button_active_bg"],
            activeforeground=theme["button_active_fg"],
        )
        self._apply_theme_to_tabs()

    def _apply_theme_to_tabs(self):
        theme = THEMES[self.theme_name]
        for index, tab in enumerate(self.tabs):
            selected = index == self.current
            button_bg = theme["button_selected_bg"] if selected else theme["button_bg"]
            button_fg = theme["button_selected_fg"] if selected else theme["button_fg"]
            border = theme["button_selected_border"] if selected else theme["tabbar_bg"]
            tab.frame.configure(
                bg=theme["tabbar_bg"],
                highlightbackground=border,
                highlightcolor=border,
            )
            tab.button.configure(
                bg=button_bg,
                fg=button_fg,
                activebackground=theme["button_active_bg"],
                activeforeground=theme["button_active_fg"],
            )
            tab.close_button.configure(
                bg=button_bg,
                fg=theme["close_fg"] if not selected else button_fg,
                activebackground=theme["button_active_bg"],
                activeforeground=theme["button_active_fg"],
            )

    def activate(self):
        self._mark_active("activate")
        try:
            self.top.deiconify()
            self.top.lift()
            self.top.focus_force()
            self.top.update_idletasks()
        except Exception:
            pass

    def _parent_id(self):
        self.top.update_idletasks()
        return self.content.winfo_id()

    def _on_resize(self, _event=None):
        if self.current is None or self.current >= len(self.tabs):
            return
        self._resize_window(self.tabs[self.current].win_id)

    def _resize_window(self, win_id):
        width = max(1, self.content.winfo_width())
        height = max(1, self.content.winfo_height())
        return _xdo("windowsize", win_id, width, height)

    def _focus_window(self, win_id):
        raised = _xdo("windowraise", win_id)
        if not raised:
            _log(logging.WARNING, "window raise failed tabber=%s win=0x%x", self.tabber_id, win_id)
        focused = _xdo("windowfocus", win_id)
        if not focused:
            _log(logging.WARNING, "window focus failed tabber=%s win=0x%x", self.tabber_id, win_id)
        return raised and focused

    def _set_outer_geometry(self, width, height):
        tabbar_h = max(1, self.tabbar.winfo_height() or 28)
        self.top.geometry(f"{max(1, width)}x{max(1, height + tabbar_h)}")

    def _resize_outer_for_tab(self, tab):
        width = tab.width or max(1, self.content.winfo_width() or 170)
        height = tab.height or max(1, self.content.winfo_height() or 40)
        self._set_outer_geometry(width, height)

    def _schedule_keepalive(self):
        if not self.top.winfo_exists():
            return
        self._keepalive()
        self._keepalive_job = self.top.after(KEEPALIVE_MS, self._schedule_keepalive)

    def _keepalive(self):
        dead = []
        for index, tab in enumerate(self.tabs):
            if not _window_exists(tab.win_id):
                dead.append(index)
        for index in reversed(dead):
            self._remove_tab(index, release=False)

    def _dismiss_menu(self, _event=None):
        if not self._menu_visible:
            return
        try:
            self._dropdown.unpost()
        except Exception:
            pass
        self._menu_visible = False

    def _on_menu_unmap(self, _event=None):
        self._menu_visible = False

    def _on_menu_click(self, _event=None):
        self.top.after_idle(self._dismiss_menu)

    def _mark_active(self, source):
        if self.on_active:
            self.on_active(self.tabber_id, source)

    def _on_focus_in(self, event=None):
        self._mark_active("focus")
        self._dismiss_menu(event)

    def _on_global_button_press(self, event):
        if not self._menu_visible:
            return
        widget_path = str(event.widget)
        menu_path = str(self._dropdown)
        if not widget_path.startswith(menu_path) and event.widget is not self.menu_button:
            self._dismiss_menu()

    def _toggle_dropdown(self):
        if self._menu_visible:
            self._dismiss_menu()
            return
        self._show_dropdown()

    def _show_dropdown(self):
        self._mark_active("dropdown")
        self._dismiss_menu()
        self._dropdown.delete(0, "end")
        self._dropdown.add_command(label="New Tabber", command=self._menu_new_tabber)
        self._dropdown.add_command(label="Add Window(s)", command=self._menu_add_windows)
        self._dropdown.add_command(label="Kill", command=self._menu_kill_current)
        self._dropdown.add_command(label="Next Tab", command=self._menu_next_tab)
        self._dropdown.add_command(label="Prev Tab", command=self._menu_prev_tab)
        self._dropdown.add_command(label="Destroy Tabber", command=self._menu_destroy_tabber)

        bx = self.menu_button.winfo_rootx()
        by = self.menu_button.winfo_rooty() + self.menu_button.winfo_height()
        self._dropdown.post(bx, by)
        self._menu_visible = True

    def _menu_new_tabber(self):
        self._mark_active("dropdown-command")
        self._dismiss_menu()
        if self.request_command:
            self.request_command("NewTabber", [], source="dropdown")
        elif self.request_new_tabber:
            self.request_new_tabber()

    def _menu_add_windows(self):
        self._mark_active("dropdown-command")
        self._dismiss_menu()
        if self.request_command:
            self.request_command("Tabize", [str(self.tabber_id)], source="dropdown")
        elif self.request_add_loop:
            self.request_add_loop(self.tabber_id)

    def _menu_kill_current(self):
        self._mark_active("dropdown-command")
        self._dismiss_menu()
        if self.current is None or self.current >= len(self.tabs):
            return
        self.kill_tab(self.tabs[self.current].win_id)

    def _menu_next_tab(self):
        self._mark_active("dropdown-command")
        self._dismiss_menu()
        if self.request_command:
            self.request_command("NextTab", [str(self.tabber_id)], source="dropdown")
        else:
            self.next_tab()

    def _menu_prev_tab(self):
        self._mark_active("dropdown-command")
        self._dismiss_menu()
        if self.request_command:
            self.request_command("PrevTab", [str(self.tabber_id)], source="dropdown")
        else:
            self.prev_tab()

    def _menu_destroy_tabber(self):
        self._mark_active("dropdown-command")
        self._dismiss_menu()
        if self.request_command:
            self.request_command("DestroyTabber", [str(self.tabber_id)], source="dropdown")
        else:
            self.destroy()

    def _tab_frame(self, title, win_id):
        frame = tk.Frame(self.tabs_holder, highlightthickness=1, bd=0)
        button = tk.Button(
            frame,
            text=title or str(win_id),
            command=lambda: self.select_by_id(win_id),
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
        )
        button.pack(side="left")

        close_button = tk.Button(
            frame,
            text="x",
            command=lambda: self.release_tab(win_id),
            relief="flat",
            bd=0,
            padx=6,
            pady=2,
        )
        close_button.pack(side="left")
        frame.pack(side="left", padx=2, pady=2)

        button.bind("<Button-3>", lambda _event, w=win_id: self.rename_tab(w))
        return frame, button, close_button

    def add_window(self, win_id, title):
        for existing in self.tabs:
            if existing.win_id == win_id:
                self.select_by_id(win_id)
                return True

        width, height = _get_window_geometry(win_id)
        parent_id = self._parent_id()
        self.activate()
        if not _xdo("windowreparent", win_id, parent_id):
            _log(logging.ERROR, "window reparent failed tabber=%s win=0x%x parent=0x%x", self.tabber_id, win_id, parent_id)
            return False

        frame, button, close_button = self._tab_frame(title, win_id)
        tab = Tab(win_id, title or str(win_id), frame, button, close_button, width=width, height=height)
        self.tabs.append(tab)

        if not _xdo("windowmap", win_id):
            _log(logging.WARNING, "window map failed after reparent tabber=%s win=0x%x", self.tabber_id, win_id)

        self._apply_theme_to_tabs()
        self.top.update_idletasks()
        if not self.select_index(len(self.tabs) - 1):
            _log(logging.ERROR, "window select failed after reparent tabber=%s win=0x%x", self.tabber_id, win_id)
            self._rollback_add_window(tab)
            return False

        _log(logging.INFO, "window added tabber=%s win=0x%x title=%r", self.tabber_id, win_id, tab.title)
        return True

    def _rollback_add_window(self, tab):
        try:
            root_id = _get_root_window_id()
            if root_id is not None:
                _xdo("windowreparent", tab.win_id, root_id)
                _xdo("windowmap", tab.win_id)
        except Exception:
            pass
        try:
            tab.frame.destroy()
        except Exception:
            pass
        try:
            self.tabs.remove(tab)
        except ValueError:
            pass
        self.current = None if not self.tabs else min(self.current or 0, len(self.tabs) - 1)
        self._apply_theme_to_tabs()

    def select_by_id(self, win_id):
        for index, tab in enumerate(self.tabs):
            if tab.win_id == win_id:
                return self.select_index(index)
        return False

    def select_index(self, idx):
        if idx < 0 or idx >= len(self.tabs):
            return False

        if self.current is not None and self.current != idx and self.current < len(self.tabs):
            old = self.tabs[self.current].win_id
            if not _xdo("windowunmap", old):
                _log(logging.WARNING, "window unmap failed tabber=%s win=0x%x", self.tabber_id, old)

        self.current = idx
        tab = self.tabs[idx]
        self.activate()
        self._resize_outer_for_tab(tab)
        mapped = _xdo("windowmap", tab.win_id)
        if not mapped:
            _log(logging.WARNING, "window map failed during select tabber=%s win=0x%x", self.tabber_id, tab.win_id)
        resized = self._resize_window(tab.win_id)
        if not resized:
            _log(logging.WARNING, "window resize failed during select tabber=%s win=0x%x", self.tabber_id, tab.win_id)
        self._focus_window(tab.win_id)
        self._apply_theme_to_tabs()
        return True

    def next_tab(self):
        if not self.tabs:
            return
        if self.current is None:
            self.select_index(0)
            return
        self.select_index((self.current + 1) % len(self.tabs))

    def prev_tab(self):
        if not self.tabs:
            return
        if self.current is None:
            self.select_index(0)
            return
        self.select_index((self.current - 1) % len(self.tabs))

    def rename_tab(self, win_id):
        for tab in self.tabs:
            if tab.win_id != win_id:
                continue
            new_name = simpledialog.askstring(
                "Rename Tab",
                "Tab name:",
                initialvalue=tab.title,
                parent=self.top,
            )
            if new_name:
                tab.title = new_name
                tab.button.configure(text=new_name)
            return

    def _remove_tab(self, idx, release=True):
        if idx < 0 or idx >= len(self.tabs):
            return

        tab = self.tabs[idx]
        if release:
            if self.on_window_released:
                self.on_window_released(tab.win_id, "manual-release")
            root_id = _get_root_window_id()
            if root_id is not None:
                if not _xdo("windowunmap", tab.win_id):
                    _log(logging.WARNING, "window unmap before release failed tabber=%s win=0x%x", self.tabber_id, tab.win_id)
                if not _xdo("windowreparent", tab.win_id, root_id):
                    _log(logging.WARNING, "window reparent release failed tabber=%s win=0x%x root=0x%x", self.tabber_id, tab.win_id, root_id)
                if not _xdo("windowmap", tab.win_id):
                    _log(logging.WARNING, "window map after release failed tabber=%s win=0x%x", self.tabber_id, tab.win_id)
        _log(logging.INFO, "window %s tabber=%s win=0x%x title=%r", "released" if release else "removed", self.tabber_id, tab.win_id, tab.title)

        try:
            tab.frame.destroy()
        except Exception:
            pass

        self.tabs.pop(idx)
        if self.current is not None:
            if self.current == idx:
                self.current = None
                if self.tabs:
                    self.select_index(min(idx, len(self.tabs) - 1))
            elif self.current > idx:
                self.current -= 1
        self._apply_theme_to_tabs()

    def release_tab(self, win_id):
        for idx, tab in enumerate(self.tabs):
            if tab.win_id == win_id:
                self._remove_tab(idx, release=True)
                return

    def kill_tab(self, win_id):
        _log(logging.INFO, "window killed tabber=%s win=0x%x", self.tabber_id, win_id)
        if not _xdo("windowkill", win_id):
            _log(logging.WARNING, "window kill failed tabber=%s win=0x%x; trying windowclose", self.tabber_id, win_id)
            if not _xdo("windowclose", win_id):
                _log(logging.WARNING, "window close fallback failed tabber=%s win=0x%x", self.tabber_id, win_id)
        for idx, tab in enumerate(self.tabs):
            if tab.win_id == win_id:
                self._remove_tab(idx, release=False)
                return

    def has_window(self, win_id):
        return any(tab.win_id == win_id for tab in self.tabs)

    def release_all(self):
        for idx in reversed(range(len(self.tabs))):
            self._remove_tab(idx, release=True)

    def destroy(self):
        self._dismiss_menu()
        if self._keepalive_job is not None:
            try:
                self.top.after_cancel(self._keepalive_job)
            except Exception:
                pass
            self._keepalive_job = None
        self.release_all()
        if self.on_destroy:
            self.on_destroy(self.tabber_id)
        try:
            self.top.destroy()
        except Exception:
            pass


# Server: socket command router, tabber registry, and autoSwallow coordinator.
class FvwmTabsServer:
    def __init__(self):
        self.config = _load_config(CONFIG_PATH)
        self.logger = _setup_logging(self.config["debug"])
        if not _import_tkinter():
            raise SystemExit(1)
        display = os.environ.get("DISPLAY", ":0")
        try:
            self.root = tk.Tk()
        except Exception as err:
            _log(logging.CRITICAL, "fatal: cannot open display %r: %s", display, err)
            print(f"FvwmTabs: cannot open display {display!r}: {err}", file=sys.stderr)
            raise SystemExit(1)
        self.root.withdraw()
        self.default_theme = self.config["theme"]
        self.auto_swallow_class = self.config["auto_swallow_class"]
        self.auto_swallow_resource = self.config["auto_swallow_resource"]
        self.auto_swallow_name = self.config["auto_swallow_name"]
        self.auto_swallow_on_startup = self.config["auto_swallow_on_startup"]
        self.tabbers = {}
        self.queue = queue.Queue()
        self.sock = None
        self._next_tabber_counter = 1
        self.active_tabber_id = None
        self._known_windows = _list_client_windows()
        self._pending_autoswallow = {}
        self._autoswallow_seen = {}
        self._autoswallow_suppressed = {}
        self._startup_scan_attempts = 0
        self._startup_scan_done = False
        self._startup_scan_job = None
        self._first_tabber_scan_done = False
        self._first_tabber_scan_job = None
        self._fallback_scan_job = None
        self._last_window_detection = time.monotonic()
        self._stop_event = threading.Event()
        self._watcher = WindowWatcher(self.queue, self._stop_event)
        self._install_signal_handlers()
        self._log_startup()

    def _log_startup(self):
        _log(logging.INFO, "%s starting", VERSION_LABEL)
        _log(logging.INFO, "config=%s socket=%s pid=%s log=%s", CONFIG_PATH, SOCKET_PATH, PID_PATH, LOG_PATH)
        _log(
            logging.INFO,
            "config loaded theme=%s debug=%s startup_scan=%s class_rules=%d resource_rules=%d name_rules=%d",
            self.default_theme,
            self.config["debug"],
            self.auto_swallow_on_startup,
            len(self.auto_swallow_class),
            len(self.auto_swallow_resource),
            len(self.auto_swallow_name),
        )
        if self.config["debug"]:
            for key in self.config["unknown_keys"]:
                _log(logging.DEBUG, "unknown config key ignored: %s", key)
        if self._autoswallow_rules_configured():
            _log(logging.INFO, "autoSwallow rules configured %s", self._format_autoswallow_rules())

    def _install_signal_handlers(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sig, self._signal_exit)
            except Exception:
                pass

    def _signal_exit(self, *_args):
        self._cleanup()
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def start(self):
        self._setup_socket()
        self.root.after(10, self._drain_queue)
        self._watcher.start()
        if self.auto_swallow_on_startup:
            self._schedule_startup_scan(500)
        if self._autoswallow_rules_configured():
            self._schedule_fallback_scan()
        self.root.mainloop()

    def _setup_socket(self):
        # The client commands are tiny one-line messages over a per-DISPLAY
        # Unix socket. A live socket means another server already owns this
        # FVWM session.
        os.makedirs(os.path.dirname(SOCKET_PATH), exist_ok=True)
        if os.path.exists(SOCKET_PATH):
            try:
                test = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test.connect(SOCKET_PATH)
                test.close()
                _log(logging.INFO, "socket already active; exiting duplicate server")
                sys.exit(0)
            except Exception:
                try:
                    os.unlink(SOCKET_PATH)
                except Exception:
                    pass

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(SOCKET_PATH)
        self.sock.listen(32)
        _log(logging.INFO, "socket listening: %s", SOCKET_PATH)

        with open(PID_PATH, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))

        atexit.register(self._cleanup)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _cleanup(self):
        # Shutdown should release windows back to root and remove only our own
        # socket/PID files.
        _log(logging.INFO, "server cleanup started")
        self._stop_event.set()
        for job in list(self._pending_autoswallow.values()):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._pending_autoswallow.clear()
        if self._startup_scan_job is not None:
            try:
                self.root.after_cancel(self._startup_scan_job)
            except Exception:
                pass
            self._startup_scan_job = None
        if self._first_tabber_scan_job is not None:
            try:
                self.root.after_cancel(self._first_tabber_scan_job)
            except Exception:
                pass
            self._first_tabber_scan_job = None
        if self._fallback_scan_job is not None:
            try:
                self.root.after_cancel(self._fallback_scan_job)
            except Exception:
                pass
            self._fallback_scan_job = None
        self._autoswallow_seen.clear()
        self._autoswallow_suppressed.clear()
        for tabber in list(self.tabbers.values()):
            try:
                tabber.on_destroy = None
                tabber.release_all()
            except Exception:
                pass
        self.tabbers.clear()
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        try:
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
        except Exception:
            pass
        try:
            if os.path.exists(PID_PATH):
                os.unlink(PID_PATH)
        except Exception:
            pass

    def _accept_loop(self):
        while not self._stop_event.is_set():
            try:
                conn, _ = self.sock.accept()
            except Exception:
                break
            threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()

    def _client_loop(self, conn):
        with conn:
            data = b""
            while True:
                try:
                    chunk = conn.recv(4096)
                except Exception:
                    break
                if not chunk:
                    break
                data += chunk
                while b"\n" in data:
                    line, data = data.split(b"\n", 1)
                    text = line.decode("utf-8", errors="ignore").strip()
                    if text:
                        self.queue.put(("command", text))

    def _drain_queue(self):
        # Tk must own UI and reparenting work, so background threads only push
        # queue messages and this method executes them in the main loop.
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break

            if kind == "command":
                self._handle_line(payload)
            elif kind == "internal_command":
                command, args, source = payload
                self._execute_command(command, args, source=source)
            elif kind == "create_tabber":
                self._create_tabber(geometry=payload)
            elif kind == "interactive_add":
                tabber_id, win_id, title = payload
                self._route_window_to_tabber(tabber_id, win_id, title)
            elif kind == "watch_windows":
                current, new_windows, removed_windows = payload
                self._handle_window_snapshot(current, new_windows, removed_windows, source="watcher")

        self.root.after(10, self._drain_queue)

    def _handle_line(self, line):
        try:
            parts = shlex.split(line)
        except Exception as err:
            _log(logging.WARNING, "command parse fallback line=%r error=%s", line, err)
            parts = line.split()
        if not parts:
            return

        self._execute_command(parts[0], parts[1:], source="socket")

    def _canonical_command(self, command):
        # Keep old FvwmConsole/client command spellings working. ConfigFvwmTabs
        # still exposes both default-tabber and explicit-ID commands.
        aliases = {
            "createnewtabber": "new_tabber",
            "newtabber": "new_tabber",
            "add": "add",
            "tabize": "tabize",
            "tabizeactive": "tabize_active",
            "nexttab": "next_tab",
            "nexttabactive": "next_tab_active",
            "prevtab": "prev_tab",
            "prevtabactive": "prev_tab_active",
            "destroytabber": "destroy_tabber",
            "destroyactivetabber": "destroy_active_tabber",
            "ping": "ping",
            "dumpautoswallow": "dump_autoswallow",
            "quit": "quit",
        }
        return aliases.get(command.strip().lower())

    def _execute_command(self, command, args=None, source="internal"):
        args = list(args or [])
        action = self._canonical_command(command)
        _log(logging.INFO, "command received source=%s command=%s args=%r action=%s", source, command, args, action)
        if action is None:
            _log(logging.WARNING, "unknown command ignored source=%s command=%s args=%r", source, command, args)
            return

        if action == "ping":
            return

        if action == "dump_autoswallow":
            self._dump_autoswallow()
            return

        if action == "new_tabber":
            geometry = self._parse_new_tabber_args(args)
            self._request_new_tabber(geometry)
            return

        if action == "add":
            if len(args) < 2:
                _log(logging.WARNING, "add command ignored: expected tabber id and window id args=%r", args)
                return
            tabber_id = _normalize_tabber_id(args[0], default=1)
            if tabber_id is None:
                _log(logging.WARNING, "add command ignored: invalid tabber id args=%r", args)
                return
            try:
                win_id = int(args[1], 0)
            except ValueError:
                _log(logging.WARNING, "add command ignored: invalid window id args=%r", args)
                return
            title = " ".join(args[2:]) if len(args) > 2 else _get_window_identity(win_id)["name"]
            self._route_window_to_tabber(tabber_id, win_id, title)
            return

        if action == "tabize":
            tabber_id = _normalize_tabber_id(args[0], default=1) if args else 1
            self._request_add_loop(tabber_id)
            return

        if action == "tabize_active":
            tabber_id = self._get_active_tabber_id()
            _log(logging.INFO, "root menu command used active tabber id=%s command=TabizeActive", tabber_id)
            self._request_add_loop(tabber_id)
            return

        if action == "next_tab":
            tabber_id = _normalize_tabber_id(args[0], default=1) if args else 1
            if tabber_id in self.tabbers:
                self.tabbers[tabber_id].next_tab()
            else:
                _log(logging.INFO, "nextTab ignored: tabber %s does not exist", tabber_id)
            return

        if action == "next_tab_active":
            tabber_id = self._get_active_tabber_id()
            _log(logging.INFO, "root menu command used active tabber id=%s command=NextTabActive", tabber_id)
            if tabber_id in self.tabbers:
                self.tabbers[tabber_id].next_tab()
            else:
                _log(logging.INFO, "nextTabActive ignored: tabber %s does not exist", tabber_id)
            return

        if action == "prev_tab":
            tabber_id = _normalize_tabber_id(args[0], default=1) if args else 1
            if tabber_id in self.tabbers:
                self.tabbers[tabber_id].prev_tab()
            else:
                _log(logging.INFO, "prevTab ignored: tabber %s does not exist", tabber_id)
            return

        if action == "prev_tab_active":
            tabber_id = self._get_active_tabber_id()
            _log(logging.INFO, "root menu command used active tabber id=%s command=PrevTabActive", tabber_id)
            if tabber_id in self.tabbers:
                self.tabbers[tabber_id].prev_tab()
            else:
                _log(logging.INFO, "prevTabActive ignored: tabber %s does not exist", tabber_id)
            return

        if action == "destroy_tabber":
            tabber_id = _normalize_tabber_id(args[0], default=1) if args else 1
            tabber = self.tabbers.pop(tabber_id, None)
            if tabber:
                _log(logging.INFO, "tabber destroyed id=%s", tabber_id)
                tabber.on_destroy = None
                tabber.destroy()
                if self.active_tabber_id == tabber_id:
                    self.active_tabber_id = None
                    _log(logging.INFO, "active tabber cleared id=%s reason=destroyed", tabber_id)
            else:
                _log(logging.INFO, "destroyTabber ignored: tabber %s does not exist", tabber_id)
            return

        if action == "destroy_active_tabber":
            tabber_id = self._get_active_tabber_id()
            _log(logging.INFO, "root menu command used active tabber id=%s command=DestroyActiveTabber", tabber_id)
            tabber = self.tabbers.pop(tabber_id, None)
            if tabber:
                _log(logging.INFO, "tabber destroyed id=%s", tabber_id)
                tabber.on_destroy = None
                tabber.destroy()
                if self.active_tabber_id == tabber_id:
                    self.active_tabber_id = None
                    _log(logging.INFO, "active tabber cleared id=%s reason=destroyed", tabber_id)
            else:
                _log(logging.INFO, "destroyActiveTabber ignored: tabber %s does not exist", tabber_id)
            return

        if action == "quit":
            _log(logging.INFO, "quit command received")
            self._cleanup()
            self.root.destroy()

    def _parse_new_tabber_args(self, args):
        geometry = None
        idx = 0
        while idx < len(args):
            arg = args[idx]
            if arg.startswith("--geometry="):
                geometry = arg.split("=", 1)[1]
                idx += 1
                continue
            if arg in ("--geometry", "-g") and idx + 1 < len(args):
                geometry = args[idx + 1]
                idx += 2
                continue
            if geometry is None and (
                arg.startswith(("+", "-")) or
                ("x" in arg and any(ch in arg for ch in "+-"))
            ):
                geometry = arg
                idx += 1
                continue
            idx += 1
        return geometry

    def _next_tabber_id(self):
        if self._next_tabber_counter < 1:
            self._next_tabber_counter = 1
        while self._next_tabber_counter in self.tabbers:
            self._next_tabber_counter += 1
        tabber_id = self._next_tabber_counter
        self._next_tabber_counter += 1
        return tabber_id

    def _create_tabber(self, tabber_id=None, geometry=None):
        # New tabbers become active immediately; focus/dropdown events can move
        # active_tabber_id later.
        had_tabbers = bool(self.tabbers)
        if tabber_id is None:
            tabber_id = self._next_tabber_id()
        else:
            tabber_id = _normalize_tabber_id(tabber_id)
        if tabber_id is None:
            return None

        if tabber_id in self.tabbers:
            existing = self.tabbers[tabber_id]
            if geometry:
                existing.top.geometry(geometry)
            existing.activate()
            return existing

        tabber = Tabber(
            self.root,
            tabber_id,
            theme_name=self.default_theme,
            geometry=geometry,
            on_destroy=self._forget_tabber,
            on_active=self._set_active_tabber,
            on_window_released=self._suppress_autoswallow,
            request_new_tabber=self._request_new_tabber,
            request_add_loop=self._request_add_loop,
            request_command=self._request_command,
        )
        self.tabbers[tabber_id] = tabber
        if self._next_tabber_counter <= tabber_id:
            self._next_tabber_counter = tabber_id + 1
        _log(logging.INFO, "tabber created id=%s geometry=%r", tabber_id, geometry)
        self._set_active_tabber(tabber_id, "created")
        if self.auto_swallow_on_startup and not self._startup_scan_done:
            self._schedule_startup_scan(250)
        if not had_tabbers and self._autoswallow_rules_configured():
            self._schedule_first_tabber_scan(500)
        return tabber

    def _request_new_tabber(self, geometry=None):
        self.queue.put(("create_tabber", geometry))

    def _request_command(self, command, args=None, source="internal"):
        self.queue.put(("internal_command", (command, list(args or []), source)))

    def _request_add_loop(self, tabber_id):
        _log(logging.INFO, "window selection cursor is controlled by FVWM/xdotool/X11, not FvwmTabs")
        threading.Thread(target=self._interactive_add_loop, args=(tabber_id,), daemon=True).start()

    def _set_active_tabber(self, tabber_id, source="unknown"):
        normalized_id = _normalize_tabber_id(tabber_id)
        if normalized_id is None:
            return
        if self.active_tabber_id != normalized_id:
            self.active_tabber_id = normalized_id
            _log(logging.INFO, "active tabber changed id=%s source=%s", normalized_id, source)

    def _get_active_tabber_id(self):
        if self.active_tabber_id in self.tabbers:
            return self.active_tabber_id
        if self.active_tabber_id is not None:
            _log(logging.INFO, "active tabber id=%s no longer exists; using default id=1", self.active_tabber_id)
            self.active_tabber_id = None
        return 1

    def _interactive_add_loop(self, tabber_id):
        root_id = _get_root_window_id()
        while not self._stop_event.is_set():
            win_id = _select_window()
            if win_id is None or win_id == root_id:
                return
            title = _get_window_identity(win_id)["name"]
            self.queue.put(("interactive_add", (tabber_id, win_id, title)))

    def _get_tabber(self, tabber_id, geometry=None, source="route"):
        normalized_id = _normalize_tabber_id(tabber_id)
        if normalized_id is None:
            return None
        if normalized_id not in self.tabbers:
            tabber = self._create_tabber(normalized_id, geometry)
            if tabber is not None:
                _log(logging.INFO, "tabber auto-created id=%s source=%s", normalized_id, source)
            return tabber
        tabber = self.tabbers[normalized_id]
        if geometry:
            tabber.top.geometry(geometry)
        return tabber

    def _tabber_exists(self, tabber_id):
        normalized_id = _normalize_tabber_id(tabber_id)
        return normalized_id is not None and normalized_id in self.tabbers

    def _forget_tabber(self, tabber_id):
        normalized_id = _normalize_tabber_id(tabber_id)
        if normalized_id is not None:
            self.tabbers.pop(normalized_id, None)
            if self.active_tabber_id == normalized_id:
                self.active_tabber_id = None
                _log(logging.INFO, "active tabber cleared id=%s reason=destroyed", normalized_id)

    def _route_window_to_tabber(self, tabber_id, win_id, title=None, source="manual"):
        # Manual add and autoSwallow both converge here so every tab follows the
        # same storage, release, kill, and destroy path.
        tabber = self._get_tabber(tabber_id, source=source)
        if tabber is None:
            _log(logging.WARNING, "route window failed: invalid tabber=%r win=0x%x", tabber_id, win_id)
            return False
        self._release_window_from_other_tabber(win_id, skip_id=tabber.tabber_id)
        return tabber.add_window(win_id, title or _get_window_identity(win_id)["name"])

    def _release_window_from_other_tabber(self, win_id, skip_id=None):
        for tabber_id, tabber in list(self.tabbers.items()):
            if tabber_id == skip_id:
                continue
            if tabber.has_window(win_id):
                tabber.release_tab(win_id)
                return

    def _handle_window_snapshot(self, current, new_windows, removed_windows, source="watcher"):
        # Removed EWMH client-list entries can be ordinary reparent side effects.
        # Only clear manual-release suppression after the X window is really gone.
        self._known_windows = current
        if new_windows:
            self._last_window_detection = time.monotonic()
        for win_id in removed_windows:
            self._cancel_pending_autoswallow(win_id)
            self._autoswallow_seen.pop(win_id, None)
            if not _window_exists(win_id):
                self._clear_autoswallow_suppression(win_id)
        for win_id in sorted(new_windows):
            if self._autoswallow_rules_configured():
                _log(logging.INFO, "autoSwallow new client window detected source=%s win=0x%x", source, win_id)
            self._handle_new_window(win_id, source=source)

    def _cancel_pending_autoswallow(self, win_id):
        job = self._pending_autoswallow.pop(win_id, None)
        if job is None:
            return
        try:
            self.root.after_cancel(job)
        except Exception:
            pass

    def _autoswallow_rules_configured(self):
        return bool(self.auto_swallow_class or self.auto_swallow_resource or self.auto_swallow_name)

    def _mark_autoswallow_seen(self, win_id):
        self._autoswallow_seen[win_id] = time.monotonic()

    def _is_autoswallow_seen(self, win_id):
        seen_at = self._autoswallow_seen.get(win_id)
        if seen_at is None:
            return False
        if time.monotonic() - seen_at > AUTOSWALLOW_CACHE_TTL:
            self._autoswallow_seen.pop(win_id, None)
            return False
        return True

    def _suppress_autoswallow(self, win_id, reason="manual-release"):
        # A released matching window is still a valid client window, so suppress
        # it briefly to prevent "release then immediately swallow again".
        self._autoswallow_suppressed[win_id] = (time.monotonic(), reason)
        self._cancel_pending_autoswallow(win_id)
        _log(logging.INFO, "autoSwallow suppressed released window win=0x%x reason=%s", win_id, reason)

    def _is_autoswallow_suppressed(self, win_id):
        item = self._autoswallow_suppressed.get(win_id)
        if item is None:
            return False
        suppressed_at, _reason = item
        if time.monotonic() - suppressed_at > AUTOSWALLOW_SUPPRESS_TTL:
            self._autoswallow_suppressed.pop(win_id, None)
            return False
        return True

    def _clear_autoswallow_suppression(self, win_id):
        self._autoswallow_suppressed.pop(win_id, None)

    def _identity_missing_for_rules(self, identity):
        if self.auto_swallow_class and not identity.get("class"):
            return True
        if self.auto_swallow_resource and not identity.get("resource"):
            return True
        if self.auto_swallow_name and not identity.get("name"):
            return True
        return False

    def _format_rule_group(self, rules):
        if not rules:
            return "[]"
        return "[" + ", ".join("%r->%s" % (pattern, tabber_id) for pattern, tabber_id in rules) + "]"

    def _format_autoswallow_rules(self):
        return (
            "class=%s resource=%s name=%s"
            % (
                self._format_rule_group(self.auto_swallow_class),
                self._format_rule_group(self.auto_swallow_resource),
                self._format_rule_group(self.auto_swallow_name),
            )
        )

    def _format_tabber_summary(self):
        if not self.tabbers:
            return "[]"
        return "[" + ", ".join(
            "id=%s tabs=%s" % (tabber_id, len(tabber.tabs))
            for tabber_id, tabber in sorted(self.tabbers.items())
        ) + "]"

    def _format_window_list(self, windows):
        if not windows:
            return "[]"
        return "[" + ", ".join("0x%x" % win_id for win_id in sorted(windows)) + "]"

    def _scan_existing_windows(self):
        # autoSwallowOnStartup is the broad startup scan. A separate first-tabber
        # safety scan exists below for the common "create tabber, then app" case.
        self._startup_scan_job = None
        if self._stop_event.is_set() or not self.auto_swallow_on_startup or self._startup_scan_done:
            return
        if not self.tabbers:
            self._startup_scan_attempts += 1
            if self._startup_scan_attempts <= 30:
                _log(logging.DEBUG, "autoSwallow startup scan waiting for first tabber attempt=%s", self._startup_scan_attempts)
                self._schedule_startup_scan(1000)
            else:
                _log(logging.INFO, "autoSwallow startup scan deferred until first tabber exists")
            return

        self._startup_scan_done = True
        self._process_autoswallow_scan("startup_scan")

    def _schedule_startup_scan(self, delay_ms):
        if self._startup_scan_job is not None or self._startup_scan_done:
            return
        self._startup_scan_job = self.root.after(delay_ms, self._scan_existing_windows)

    def _scan_after_first_tabber(self):
        self._first_tabber_scan_job = None
        if self._stop_event.is_set() or self._first_tabber_scan_done or not self._autoswallow_rules_configured():
            return
        self._first_tabber_scan_done = True
        if not self.tabbers:
            _log(logging.INFO, "autoSwallow first-tabber safety scan skipped: no tabbers exist")
            return
        self._process_autoswallow_scan("first_tabber_scan")

    def _schedule_first_tabber_scan(self, delay_ms):
        if self._first_tabber_scan_job is not None or self._first_tabber_scan_done:
            return
        self._first_tabber_scan_job = self.root.after(delay_ms, self._scan_after_first_tabber)

    def _fallback_scan_windows(self):
        # Polling _NET_CLIENT_LIST is intentionally simple; this periodic pass
        # catches windows missed between watcher snapshots without reprocessing
        # known clients.
        self._fallback_scan_job = None
        try:
            if self._stop_event.is_set() or not self._autoswallow_rules_configured():
                return
            idle_seconds = time.monotonic() - self._last_window_detection
            if idle_seconds < (AUTOSWALLOW_FALLBACK_SCAN_MS / 1000.0):
                return
            current = _list_client_windows()
            new_windows = current - self._known_windows
            removed_windows = self._known_windows - current
            if new_windows:
                _log(
                    logging.INFO,
                    "autoSwallow fallback scan found unknown_windows=%d current_windows=%d",
                    len(new_windows),
                    len(current),
                )
            self._handle_window_snapshot(current, new_windows, removed_windows, source="fallback_scan")
        finally:
            self._schedule_fallback_scan()

    def _schedule_fallback_scan(self):
        if self._fallback_scan_job is not None or self._stop_event.is_set() or not self._autoswallow_rules_configured():
            return
        self._fallback_scan_job = self.root.after(AUTOSWALLOW_FALLBACK_SCAN_MS, self._fallback_scan_windows)

    def _process_autoswallow_scan(self, source):
        current = _list_client_windows()
        removed_windows = self._known_windows - current
        self._known_windows = current
        for win_id in removed_windows:
            self._cancel_pending_autoswallow(win_id)
            self._autoswallow_seen.pop(win_id, None)
            if not _window_exists(win_id):
                self._clear_autoswallow_suppression(win_id)
        _log(logging.INFO, "autoSwallow scan source=%s windows=%d", source, len(current))
        for win_id in sorted(current):
            if self._is_autoswallow_seen(win_id):
                _log(logging.DEBUG, "autoSwallow scan skip source=%s win=0x%x reason=already-seen", source, win_id)
                continue
            _log(logging.INFO, "autoSwallow scan candidate source=%s win=0x%x", source, win_id)
            self._handle_new_window(win_id, source=source)

    def _handle_new_window(self, win_id, retries_left=AUTOSWALLOW_RETRIES, source="watcher"):
        # Candidate filtering is ordered from cheap/local checks to xprop-heavy
        # identity work and finally to rule matching/routing.
        if not self._autoswallow_rules_configured():
            return
        if win_id not in self._known_windows:
            self._cancel_pending_autoswallow(win_id)
            _log(logging.DEBUG, "autoSwallow skip source=%s win=0x%x reason=not-in-client-list", source, win_id)
            return
        if self._is_autoswallow_suppressed(win_id):
            self._cancel_pending_autoswallow(win_id)
            _log(logging.INFO, "autoSwallow skip reason=manual-release-suppressed source=%s win=0x%x", source, win_id)
            return
        if self._is_autoswallow_seen(win_id):
            _log(logging.DEBUG, "autoSwallow skip source=%s win=0x%x reason=already-seen", source, win_id)
            return
        if self._is_internal_window(win_id):
            self._mark_autoswallow_seen(win_id)
            self._cancel_pending_autoswallow(win_id)
            _log(logging.INFO, "autoSwallow skipped internal/tabbed window source=%s win=0x%x", source, win_id)
            return

        identity = _get_window_identity(win_id)
        identity_log_level = logging.INFO if retries_left == AUTOSWALLOW_RETRIES else logging.DEBUG
        _log(identity_log_level, "autoSwallow identity parsed source=%s retries_left=%s %s", source, retries_left, _format_identity(identity))
        skip_reason = self._autoswallow_skip_reason(identity)
        if skip_reason:
            self._mark_autoswallow_seen(win_id)
            self._cancel_pending_autoswallow(win_id)
            _log(
                logging.INFO,
                "autoSwallow skipped transient/menu/dialog window source=%s reason=%s %s",
                source,
                skip_reason,
                _format_identity(identity),
            )
            return

        target_id, rule_kind, pattern = self._match_autoswallow_target(identity)
        if target_id is not None:
            target_existed = self._tabber_exists(target_id)
            _log(
                logging.INFO,
                "autoSwallow rule matched source=%s win=0x%x rule=%s:%r target_tabber=%s %s",
                source,
                win_id,
                rule_kind,
                pattern,
                target_id,
                _format_identity(identity),
            )
            _log(
                logging.INFO,
                "autoSwallow route attempted source=%s win=0x%x target_tabber=%s target_existed=%s",
                source,
                win_id,
                target_id,
                target_existed,
            )
            routed = self._route_window_to_tabber(
                target_id,
                win_id,
                identity["name"] or str(win_id),
                source="autoSwallow",
            )
            _log(
                logging.INFO if routed else logging.WARNING,
                "autoSwallow route %s source=%s win=0x%x rule=%s:%r target_tabber=%s target_existed=%s",
                "succeeded" if routed else "failed",
                source,
                win_id,
                rule_kind,
                pattern,
                target_id,
                target_existed,
            )
            if routed:
                self._mark_autoswallow_seen(win_id)
                self._cancel_pending_autoswallow(win_id)
                return

            _log(logging.WARNING, "autoSwallow route failed source=%s win=0x%x target=%s retries_left=%s", source, win_id, target_id, retries_left)
            if retries_left <= 1:
                self._mark_autoswallow_seen(win_id)
                self._cancel_pending_autoswallow(win_id)
                return
            self._schedule_autoswallow_retry(win_id, retries_left - 1, identity, source)
            return

        missing_needed_identity = self._identity_missing_for_rules(identity)
        if retries_left <= 1 or not missing_needed_identity:
            self._mark_autoswallow_seen(win_id)
            self._cancel_pending_autoswallow(win_id)
            _log(
                logging.INFO,
                (
                    "autoSwallow no rule matched source=%s win=0x%x reason=%s retries_left=%s "
                    "resource=%r class=%r name=%r rules=%s; restart FvwmTabs after changing autoSwallow config"
                ),
                source,
                win_id,
                "identity-incomplete" if missing_needed_identity else "no-matching-rule",
                retries_left,
                identity.get("resource", ""),
                identity.get("class", ""),
                identity.get("name", ""),
                self._format_autoswallow_rules(),
            )
            return

        if retries_left == AUTOSWALLOW_RETRIES:
            _log(
                logging.INFO,
                "autoSwallow identity incomplete; retry scheduled source=%s win=0x%x retries_left=%s %s",
                source,
                win_id,
                retries_left - 1,
                _format_identity(identity),
            )
        self._schedule_autoswallow_retry(win_id, retries_left - 1, identity, source)

    def _schedule_autoswallow_retry(self, win_id, retries_left, identity, source):
        self._cancel_pending_autoswallow(win_id)
        _log(logging.DEBUG, "autoSwallow retry source=%s win=0x%x retries_left=%s %s", source, win_id, retries_left, _format_identity(identity))
        self._pending_autoswallow[win_id] = self.root.after(
            AUTOSWALLOW_RETRY_MS,
            lambda wid=win_id, retries=retries_left, src=source: self._handle_new_window(wid, retries, src),
        )

    def _autoswallow_skip_reason(self, identity):
        role = (identity.get("role") or "").lower()
        window_type = (identity.get("window_type") or "").lower()
        if identity.get("transient_for"):
            return "transient-window"
        if any(term in role for term in ("popup", "pop-up", "menu", "dialog", "tooltip")):
            return "window-role"
        if any(term in window_type for term in ("menu", "dialog", "splash", "tooltip", "dropdown", "popup")):
            return "window-type"
        if self._is_override_redirect(identity["id"]):
            return "override-redirect"
        return None

    def _is_override_redirect(self, win_id):
        try:
            out = _run_capture(["xwininfo", "-id", str(win_id)])
        except Exception:
            return False
        for line in out.splitlines():
            if "Override Redirect State:" in line:
                return line.rsplit(":", 1)[1].strip().lower() == "yes"
        return False

    def _is_internal_window(self, win_id):
        for tabber in self.tabbers.values():
            try:
                if tabber.top.winfo_exists() and tabber.top.winfo_id() == win_id:
                    return True
            except Exception:
                pass
            if tabber.has_window(win_id):
                return True
        return False

    def _match_autoswallow_target(self, identity):
        # Match stable WM_CLASS class first. Resource and title rules stay for
        # compatibility with older FvwmTabs configs and odd applications.
        for pattern, tabber_id in self.auto_swallow_class:
            if _matches_pattern(pattern, identity.get("class", "")):
                return tabber_id, "class", pattern
        for pattern, tabber_id in self.auto_swallow_resource:
            if _matches_pattern(pattern, identity.get("resource", "")):
                return tabber_id, "resource", pattern
        for pattern, tabber_id in self.auto_swallow_name:
            if _matches_pattern(pattern, identity.get("name", "")):
                return tabber_id, "name", pattern
        return None, None, None

    def _dump_autoswallow(self):
        current, details = _get_client_window_snapshot()
        _log(logging.INFO, "dumpAutoSwallow tabbers=%s", self._format_tabber_summary())
        _log(logging.INFO, "dumpAutoSwallow rules=%s", self._format_autoswallow_rules())
        for prop in CLIENT_LIST_PROPERTIES:
            prop_details = details.get(prop, {"available": False, "windows": set()})
            _log(
                logging.INFO,
                "dumpAutoSwallow %s available=%s windows=%s",
                prop,
                prop_details["available"],
                self._format_window_list(prop_details["windows"]),
            )
        _log(
            logging.INFO,
            "dumpAutoSwallow merged_client_windows count=%d windows=%s",
            len(current),
            self._format_window_list(current),
        )
        for win_id in sorted(current):
            identity = _get_window_identity(win_id)
            target_id, rule_kind, pattern = self._match_autoswallow_target(identity)
            match = "none"
            if target_id is not None:
                match = "%s:%r->%s" % (rule_kind, pattern, target_id)
            skip_reason = None
            if self._is_internal_window(win_id):
                skip_reason = "internal-or-already-tabbed"
            else:
                skip_reason = self._autoswallow_skip_reason(identity)
            _log(
                logging.INFO,
                "dumpAutoSwallow window %s match=%s skip=%s",
                _format_identity(identity),
                match,
                skip_reason or "none",
            )


def main():
    if _LOGGER is None:
        _setup_logging(False)
    try:
        server = FvwmTabsServer()
        server.start()
    except Exception:
        if _LOGGER is not None:
            _LOGGER.exception("fatal server error")
        raise


if __name__ == "__main__":
    main()
