#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import socket
import stat
import threading


DEFAULT_EVENTS = ("new_window", "map", "destroy_window")
ENV_SOCKET_KEYS = ("FVWMMFL_SOCKET", "FVWMMFL_SOCKET_PATH")


class FvwmMFLClient:
    """Small FvwmMFL Unix-socket client for FVWM commands and JSON events."""

    def __init__(self, socket_path=None, logger=None, connect_timeout=1.0):
        self.socket_path = socket_path
        self.logger = logger or logging.getLogger("FvwmTabs")
        self.connect_timeout = connect_timeout
        self.active_socket_path = None
        self._decoder = json.JSONDecoder()

    def configured(self):
        return bool(self.socket_path or any(os.environ.get(key) for key in ENV_SOCKET_KEYS))

    def candidate_paths(self):
        paths = []
        if self.socket_path:
            paths.append(self.socket_path)
        else:
            for key in ENV_SOCKET_KEYS:
                value = os.environ.get(key)
                if value:
                    paths.append(value)

        unique = []
        seen = set()
        for path in paths:
            if path and path not in seen:
                unique.append(path)
                seen.add(path)
        return unique

    def locate_socket(self):
        for path in self.candidate_paths():
            try:
                mode = os.stat(path).st_mode
            except FileNotFoundError:
                continue
            except OSError as err:
                self._log(logging.DEBUG, "FvwmMFL socket stat failed path=%s error=%s", path, err)
                continue
            if stat.S_ISSOCK(mode):
                self.active_socket_path = path
                return path
        return None

    def available(self):
        return self.locate_socket() is not None

    def can_connect(self):
        sock = self._connect()
        if sock is None:
            return False
        try:
            return True
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _connect(self):
        path = self.locate_socket()
        if not path:
            return None
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.connect_timeout)
        try:
            sock.connect(path)
        except OSError as err:
            self._log(logging.DEBUG, "FvwmMFL connect failed path=%s error=%s", path, err)
            sock.close()
            return None
        return sock

    def send_command(self, command):
        command = str(command or "").strip()
        if not command:
            return False
        sock = self._connect()
        if sock is None:
            self._log(logging.DEBUG, "FvwmMFL unavailable; FVWM command not sent command=%r", command)
            return False
        try:
            sock.sendall((command + "\n").encode("utf-8"))
            self._log(logging.DEBUG, "FvwmMFL command sent socket=%s command=%r", self.active_socket_path, command)
            return True
        except OSError as err:
            self._log(logging.WARNING, "FvwmMFL command send failed command=%r error=%s", command, err)
            return False
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def start_event_listener(self, events, callback, stop_event=None, reconnect_delay=2.0):
        events = tuple(events or DEFAULT_EVENTS)
        stop_event = stop_event or threading.Event()
        thread = threading.Thread(
            target=self._event_loop,
            args=(events, callback, stop_event, reconnect_delay),
            daemon=True,
        )
        thread.start()
        return thread

    def _event_loop(self, events, callback, stop_event, reconnect_delay):
        while not stop_event.is_set():
            sock = self._connect()
            if sock is None:
                stop_event.wait(reconnect_delay)
                continue
            try:
                sock.settimeout(1.0)
                for event in events:
                    sock.sendall((f"set {event}\n").encode("utf-8"))
                self._log(
                    logging.INFO,
                    "FvwmMFL event listener connected socket=%s events=%s",
                    self.active_socket_path,
                    ",".join(events),
                )
                self._read_events(sock, callback, stop_event)
            except OSError as err:
                if not stop_event.is_set():
                    self._log(logging.WARNING, "FvwmMFL event listener disconnected error=%s", err)
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
            stop_event.wait(reconnect_delay)

    def _read_events(self, sock, callback, stop_event):
        buffer = ""
        while not stop_event.is_set():
            try:
                chunk = sock.recv(32768)
            except socket.timeout:
                continue
            if not chunk:
                return
            buffer += chunk.decode("utf-8", errors="replace")
            buffer = self._dispatch_json_buffer(buffer, callback)

    def _dispatch_json_buffer(self, buffer, callback):
        while buffer:
            stripped = buffer.lstrip()
            if stripped != buffer:
                buffer = stripped
            if not buffer:
                return ""
            try:
                packet, index = self._decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                if "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            callback(json.loads(line))
                        except Exception as err:
                            self._log(logging.DEBUG, "FvwmMFL JSON line ignored line=%r error=%s", line, err)
                    continue
                return buffer
            try:
                callback(packet)
            except Exception as err:
                self._log(logging.WARNING, "FvwmMFL event callback failed packet=%r error=%s", packet, err)
            buffer = buffer[index:]
        return buffer

    def subscribe(self, events):
        sock = self._connect()
        if sock is None:
            return False
        try:
            for event in events:
                sock.sendall((f"set {event}\n").encode("utf-8"))
            return True
        except OSError as err:
            self._log(logging.WARNING, "FvwmMFL subscribe failed events=%s error=%s", events, err)
            return False
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _log(self, level, message, *args):
        if self.logger:
            self.logger.log(level, message, *args)


def extract_event_window_id(packet):
    """Return (event_name, window_id) from a FvwmMFL JSON packet when present."""
    if not isinstance(packet, dict) or not packet:
        return None, None
    event_name, payload = next(iter(packet.items()))
    return event_name, _find_window_id(payload)


def _find_window_id(value):
    if isinstance(value, dict):
        for key in ("window", "window_id", "id"):
            if key in value:
                parsed = _parse_window_id(value[key])
                if parsed is not None:
                    return parsed
        for item in value.values():
            parsed = _find_window_id(item)
            if parsed is not None:
                return parsed
    elif isinstance(value, (list, tuple)):
        for item in value:
            parsed = _find_window_id(item)
            if parsed is not None:
                return parsed
    return _parse_window_id(value)


def _parse_window_id(value):
    if isinstance(value, int):
        return value if value > 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        return None
