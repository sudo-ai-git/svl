"""USB-serial transport: the primary way the host reaches a Flipper.

Opens the serial port, tries the most common baud rates, and provides
read/write. Connect auto-detects the port when none is given.

Wire protocol: newline-separated UTF-8 command/response lines (see base).
"""

from __future__ import annotations

import glob
import os
import time
from typing import Callable

import serial

from .base import Transport

_DEFAULT_BAUD = 115200
_DEFAULT_TIMEOUT = 0.5
_BAUD_CANDIDATES = (9600, 115200, 230400, 921600, 1000000)


class UsbSerialTransport(Transport):
    """USB-serial wrapper around pyserial.

    Wire protocol: newline-separated UTF-8 command/response lines (see base).
    A command that sends a line and then reads a bounded reply works through
    ``receive(timeout)`` in a polling loop.

    Baud is not assumed: :meth:`connect` probes the most common rates and keeps
    the first that opens. Flipper data ports are commonly **9600 / 115200 /
    230400**.
    """


    def __init__(self, path: str = "", baud: int = _DEFAULT_BAUD,
                 receive_timeout: float = 0.1) -> None:
        self.path = path
        self.baud = baud
        self.receive_timeout = receive_timeout
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
        ok, baud = self._try_baud(self.path)
        if not ok:
            return False
        self.baud = baud
        try:
            self._port = serial.Serial(
                self.path, self.baud,
                timeout=0.0,          # we poll ourselves in receive()
                write_timeout=0.5,
            )
            return True
        except serial.SerialException as exc:
            self._port = None
            if self._emitter is not None:
                self._emitter(self, "error",
                               f"cannot open {self.path}: {exc}")
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

    def receive(self, timeout: float = 0.05) -> bytes:
        """Poll until `timeout` seconds have elapsed, returning any bytes
        that have arrived. Respects the transport's own read timeout."""
        if self._port is None or not self._port.is_open:
            return b""
        try:
            if self._port.in_waiting:
                return self._port.read(self._port.in_waiting)
            if timeout <= 0.0:
                return b""
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if self._port.in_waiting:
                    return self._port.read(self._port.in_waiting)
                time.sleep(0.02)
            return b""
        except (OSError, serial.SerialException):
            self.disconnect()
            return b""

    def on_event(self, emitter: Callable[[Transport, str, object], None]) -> None:
        self._emitter = emitter

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def probe(cls) -> str | None:
        """Return the first Flipper-like serial device on this host."""
        patterns = {
            "/dev/ttyACM*",           # Linux (STM32 CDC)
            "/dev/ttyUSB*",           # Linux (FTDI/PL2303 adapters)
            "/dev/cu.usbmodem*",      # macOS
            "/dev/cu.usbserial*",     # macOS (FTDI)
            "COM3", "COM4",
        }
        for pattern in patterns:
            for path in glob.glob(pattern):
                if os.path.exists(path):
                    return path
        return None

    def _probe(self) -> str | None:
        return self.probe()

    @staticmethod
    def _try_baud(path: str) -> tuple[bool, int]:
        """Try each candidate baud. Returns (opened_ok, baud_used)."""
        for baud in _BAUD_CANDIDATES:
            try:
                probe_port = serial.Serial(path, baud, timeout=_DEFAULT_TIMEOUT)
                probe_port.close()
                return True, baud
            except (OSError, serial.SerialException):
                continue
        return False, _DEFAULT_BAUD
