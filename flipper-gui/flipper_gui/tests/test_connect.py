"""End-to-end tests for the "connect" path (discovery + open + reply).

These exercise the DeviceManager and the Device.request() send/reply cycle
with a controllable fake Flipper, so the connection mechanism is verified by
execution rather than asserted from code.
"""

from __future__ import annotations

import sys

import pytest  # noqa: F401

from flipper_gui.comm.device_manager import (
    CandidateKind,
    DeviceCandidate,
    DeviceManager,
)
from flipper_gui.comm.usb_serial import UsbSerialTransport
from flipper_gui.core.commands import Command
from flipper_gui.core.devices import Device, DeviceType
from flipper_gui.core.registry import CommandRegistry


class _MockSerialTransport:
    """A controllable stand-in for the Flipper's serial port."""

    def __init__(self, path: str = "/dev/ttyS0", baud: int = 115200) -> None:
        self.path = path
        self.baud = baud
        self._connected = False
        self._tx = b""
        self._rx: list[bytes] = []
        self._emitted = False  # emit the canned reply exactly once

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def send(self, data: bytes) -> bool:
        self._tx += data
        return True

    def receive(self, timeout: float = 0.05) -> bytes:
        # Stream a canned reply exactly once; a real Flipper finishes after
        # sending its data instead of repeating it (repeats trip the idle
        # guard and hang the reply).
        if not self._emitted:
            self._emitted = True
            self._rx = [b"model: Flipper Zero", b"channel: RELEASE"]
        if self._rx:
            data = b"\n".join(self._rx) + b"\n"
            self._rx = []
            return data
        return b""


class TestDeviceManager:
    def test_serial_candidates(self) -> None:
        cands = DeviceManager().discover()
        kinds = {c.kind for c in cands}
        assert CandidateKind.SERIAL in kinds

    def test_ble_defers_import(self) -> None:
        # bleak must not be imported when the module loads (headless boxes).
        from flipper_gui.comm import device_manager as dm

        before = set(sys.modules)
        DeviceManager()
        after = set(sys.modules)
        assert not any("bleak" in k for k in after.difference(before))


class TestConnectFlow:
    def _make_device(self, transport, registry) -> Device:
        dev = Device(device_type=DeviceType.USB_SERIAL, transport=transport)
        dev.set_events(None)
        if registry:
            dev.registry = registry
        return dev

    def test_request_send_read_roundtrip(self) -> None:
        transport = _MockSerialTransport()
        reg = CommandRegistry()
        reg.register(Command(name="fw", description="firmware info"))
        device = self._make_device(transport, reg)
        device.connect()  # wire the transport, so info.connected is set
        lines = device.request("fw", ["433920000"])
        assert device.is_connected() is True
        assert lines == ["model: Flipper Zero", "channel: RELEASE"]
        # wire line was exactly 'fw 433920000'
        assert bytes(transport._tx) == b"fw 433920000\n"

    def test_request_returns_empty_without_registry(self) -> None:
        transport = _MockSerialTransport()
        device = Device(device_type=DeviceType.USB_SERIAL, transport=transport)
        device.set_events(None)
        assert device.request("fw") == []

    def test_register_commands(self) -> None:
        from flipper_gui.core.registry import CommandRegistry

        transport = _MockSerialTransport()
        reg = CommandRegistry()
        reg.register(Command(name="nfc", description="NFC read"))
        reg.register(Command(name="rfid", description="RFID read"))
        device = self._make_device(transport, reg)
        device.connect()  # open the transport + set info.connected
        assert device.request("rfid") == ["model: Flipper Zero", "channel: RELEASE"]
        assert device.request("sub-ghz") == []
