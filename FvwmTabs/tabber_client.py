#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shlex
import socket
import subprocess
import sys
import time

STARTUP_TIMEOUT = 2.0
STARTUP_RETRY_DELAY = 0.1


# Client-side wrapper used by FVWM functions. It starts the long-running Tk
# server when needed, then sends one shell-quoted command over the session socket.
def _session_suffix():
    display = os.environ.get("DISPLAY", ":0")
    safe_display = display.replace(":", "").replace(".", "_")
    safe_display = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in safe_display)
    return safe_display or "0"


SOCKET_PATH = os.path.expanduser(f"~/.fvwm/.fvwmtabs-{_session_suffix()}.sock")


def _shlex_join(args):
    try:
        return shlex.join(args)
    except AttributeError:
        return " ".join(shlex.quote(arg) for arg in args)


def _normalize_tabber_id(value, default=None):
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    if text.lower() == "default":
        return "1"
    try:
        tabber_id = int(text)
    except Exception:
        return default
    if tabber_id <= 0:
        return default
    return str(tabber_id)


def _normalize_args(argv):
    if not argv:
        return argv

    command = argv[0]
    args = list(argv[1:])

    if command.lower() in {"add", "tabize", "nexttab", "prevtab", "destroytabber"} and args:
        args[0] = _normalize_tabber_id(args[0], default="1") or "1"

    if command.lower() in {"createnewtabber", "newtabber"} and args:
        filtered_args = []
        for arg in args:
            if filtered_args:
                filtered_args.append(arg)
                continue
            if arg in ("--geometry", "-g") or arg.startswith("--geometry="):
                filtered_args.append(arg)
                continue
            if arg.startswith(("+", "-")) or ("x" in arg and any(ch in arg for ch in "+-")):
                filtered_args.append(arg)
                continue
            normalized = _normalize_tabber_id(arg)
            if normalized is not None:
                continue
            filtered_args.append(arg)
        args = filtered_args

    return [command] + args


def _socket_available():
    try:
        _send_line("ping")
        return True
    except Exception:
        return False


def _wait_for_server(timeout=STARTUP_TIMEOUT, delay=STARTUP_RETRY_DELAY):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _socket_available():
            return True
        time.sleep(delay)
    return False


def _start_server():
    if _socket_available():
        return True
    server_path = os.path.join(os.path.dirname(__file__), "FvwmTabs.py")
    try:
        subprocess.Popen(
            [sys.executable, server_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as err:
        print(f"FvwmTabs: failed to start server: {err}", file=sys.stderr)
        return False
    if _wait_for_server():
        return True
    print(
        f"FvwmTabs: server did not answer on {SOCKET_PATH} after {STARTUP_TIMEOUT:.1f}s; "
        "check ~/.fvwm/fvwmtabs.log",
        file=sys.stderr,
    )
    return False


def _send_line(line):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(SOCKET_PATH)
        sock.sendall((line + "\n").encode("utf-8"))


def _send_with_retry(line, retries=8, delay=0.1):
    for _ in range(retries):
        try:
            _send_line(line)
            return True
        except Exception:
            time.sleep(delay)
    return False


def main():
    if len(sys.argv) < 2:
        return 1

    if sys.argv[1] == "start":
        return 0 if _start_server() else 1

    line = _shlex_join(_normalize_args(sys.argv[1:]))
    try:
        _send_line(line)
        return 0
    except Exception:
        if not _start_server():
            return 1
        if _send_with_retry(line):
            return 0
        print(
            f"FvwmTabs: server did not answer on {SOCKET_PATH}; "
            "check ~/.fvwm/fvwmtabs.log or remove stale .fvwmtabs-*.sock/.fvwmtabs-*.pid",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
