"""Tests for the core device model and the command registry."""

from __future__ import annotations

import pytest

from flipper_gui.core.commands import Command
from flipper_gui.core.devices import Device, DeviceInfo, DeviceType, Capability
from flipper_gui.core.registry import CommandRegistry


class DummyTransport:
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


def test_device_basic() -> None:
    dev = Device(device_type=DeviceType.USB_SERIAL)
    assert dev.is_connected() is False


def test_device_connect_delegates() -> None:
    tx = DummyTransport()
    dev = Device(device_type=DeviceType.USB_SERIAL, transport=tx)
    assert dev.is_connected() is False
    assert dev.connect() is True
    assert dev.is_connected() is True
    dev.disconnect()
    assert dev.is_connected() is False


def test_device_command_without_registry_returns_none() -> None:
    dev = Device(device_type=DeviceType.USB_SERIAL, registry=None)
    assert dev.command("list") is None


class TestCommandRegistry:
    def test_register_and_lookup(self) -> None:
        reg = CommandRegistry()
        cmd = Command(
            name="list",
            description="list things",
            handler=lambda d, a, p: ["ok"],
        )
        from flipper_gui.core.registry import register
        register(reg, cmd)
        assert reg.has("list")
        assert reg.describe("list") == "list things"


class TestCapability:
    def test_available_only_when_connected(self) -> None:
        dev = Device(device_type=DeviceType.USB_SERIAL)
        cap = Capability(name="nfc", enabled=True)
        assert cap.is_available(dev) is False
