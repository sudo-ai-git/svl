"""USB-serial transport: the primary way the host reaches a Flipper.

Opens the serial port, sets a sane baud for the Flipper's data/UART path,
and provides read/write. Connect auto-detects the port when none is given.
"""

from __future__ import annotations

import glob
import os
import time
from typing import Callable

import serial

from .base import Transport

_DEFAULT_BAUD = 115200
_RECONNECT_DELAY = 0.5


class UsbSerialTransport(Transport):
    """USB-serial wrapper around pyserial."""

    def __init__(self, path: str = "", baud: int = _DEFAULT_BAUD, timeout: float = 0.5) -> None:
        self.path = path
        self.baud = baud
        self.timeout = timeout
        self._port: serial.Serial | None = None
        self._emitter: Callable[[Transport, str, object], None] | None = None

    # ------------------------------------------------------------------ #
    # Transport interface
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        if self._port is not None and self._port.is_open:
            return True
        if not self.path:
            self.path = self._probe()
            if not self.path:
                return False
        try:
            self._port = serial.Serial(self.path, self.baud, timeout=0.5, write_timeout=0.5)
            return True
        except serial.SerialException as exc:
            self._port = None
            self._emitter and self._emitter(self, "error", f"cannot open {self.path}: {exc}")
            return False

    def disconnect(self) -> None:
        if self._port is not None and self._port.is_open:
            try:
                self._port.close()
            except Exception:
                pass
        self._port = None

    def send(self, data: bytes) -> bool:
        if self._port is None or not self._port.is_open:
            return False
        try:
            self._port.write(data)
            return True
        except (OSError, serial.SerialException):
            return False

    def receive(self) -> bytes | None:
        if self._port is None or not self._port.is_open:
            return None
        try:
            if self._port.in_waiting:
                return self._port.read(self._port.in_waiting)
        except (OSError, serial.SerialException):
            self.disconnect()
        return None

    def on_event(self, emitter: Callable[[Transport, str, object], None]) -> None:
        self._emitter = emitter

    def command(self, name: str, args: list[str] | None = None, payload: object | None = None) -> list[str] | None:
        # USB-serial backends speak a newline/text protocol; override per device.
        return None

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def probe(cls) -> str | None:
        """Return the first Flipper-like serial device on this host."""
        patterns = {
            "/dev/ttyACM*",
            "/dev/ttyUSB*",
            "/dev/cu.usbmodem*",
            "/dev/cu.usbserial*",
            "COM3",
            "COM4",
        }
        for pattern in patterns:
            for path in glob.glob(pattern):
                if os.path.exists(path):
                    return path
        return None

    def _probe(self) -> str | None:
        return self.probe()
