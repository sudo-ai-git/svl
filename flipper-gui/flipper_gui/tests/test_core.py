"""Tests for the core domain (devices, commands, registry) and the comm
session. These do not require a GUI backend or a physical Flipper.
"""

from __future__ import annotations

import pytest

from flipper_gui.core.commands import Command, PAYLOAD_TEXT, PAYLOAD_JSON, PAYLOAD_BYTES
from flipper_gui.core.devices import Device, DeviceInfo, DeviceType, Capability
from flipper_gui.core.registry import CommandRegistry, register


class DummyTransport:
    """Minimal fake transport for tests."""

    def __init__(self) -> None:
        self.connected = False
        self.received: list[bytes] = []

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def send(self, data: bytes) -> bool:
        return True

    def receive(self) -> bytes | None:
        return None

    def on_event(self, emitter):  # type: ignore[func-returns-value]
        pass


class DummyDevice(Device):
    def __init__(self, **kwargs) -> None:
        super().__init__(device_type=DeviceType.USB_SERIAL, transport=DummyTransport(), **kwargs)
        self.backend = self.transport
        self.connected = True
        self.info.connected = True
        self.events = None


class TestCommands:
    def test_default_payload(self) -> None:
        cmd = Command(name="echo")
        assert cmd.payload == PAYLOAD_TEXT

    def test_payload_variants(self) -> None:
        assert PAYLOAD_JSON == "json"
        assert PAYLOAD_BYTES == "bytes"

    def test_requires_connected(self) -> None:
        cmd = Command(name="x", requires_connected=True)
        assert cmd.requires_connected


class TestRegistry:
    def test_register_and_lookup(self) -> None:
        reg = CommandRegistry()
        cmd = Command(name="list", description="list things", handler=lambda d, a, p: ["ok"])
        register(reg, cmd)
        assert reg.has("list")
        assert reg.describe("list") == "list things"
        assert reg.list_commands() == ["list"]


class TestDevice:
    def test_connect_and_disconnect(self) -> None:
        dev = Device(
            device_type=DeviceType.USB_SERIAL,
            transport=DummyTransport(),
            info=DeviceInfo(connected=False),
        )
        assert dev.is_connected() is False
        assert dev.connect() is True
        assert dev.is_connected() is True
        dev.disconnect()
        assert dev.is_connected() is False

    def test_request_with_no_registry_returns_empty(self) -> None:
        dev = DummyDevice(registry=None)
        assert dev.request("x") == []
