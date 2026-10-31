"""Tests for the core device model and the command registry."""

from __future__ import annotations

import pytest
import sys
from unittest import mock

from flipper_gui.core.commands import Command
from flipper_gui.core.devices import Device, DeviceInfo, DeviceType, Capability
from flipper_gui.core.registry import CommandRegistry


class DummyTransport:
    """Transport stub whose :meth:`receive` takes the ``timeout`` kwarg that
    :class:`Protocol` expects and returns canned reply bytes."""

    def __init__(self) -> None:
        self.connected = False
        self.received: list[bytes] = []
        self.canned_reply: bytes = b""
        self._consumed = False

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def send(self, data: bytes) -> bool:
        return True

    def receive(self, timeout: float = 0.05) -> bytes:
        # Deliver the canned reply exactly once, then go quiet so the
        # Protocol's stability guard settles the reply (tested behaviour).
        if self._consumed:
            return b""
        self._consumed = True
        return self.canned_reply

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


def test_request_with_no_registry_returns_empty() -> None:
    dev = Device(device_type=DeviceType.USB_SERIAL, registry=None)
    assert dev.request("list") == []


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


    def test_request_emits_data_received(self) -> None:
        from flipper_gui.core.registry import CommandRegistry, register
        rec = mock.Mock()
        dev = Device(device_type=DeviceType.USB_SERIAL, events=rec)
        dev.transport = DummyTransport()
        dev.connect()  # sets info.connected and emits device.connected
        reg = CommandRegistry()
        register(reg, Command(
            name="fw", description="fw command",
            handler=lambda d, a, p: ["model: Flipper Zero"],
        ))
        dev.registry = reg

        dev.transport.canned_reply = b"model: Flipper Zero\nchannel: RELEASE\n"
        reply = dev.request("fw")
        assert reply == ["model: Flipper Zero", "channel: RELEASE"]
        print(">>> EVENTS:", rec.call_args_list, file=sys.stderr)
        # c is a _mock_call: c[0]==args-tuple, c[1]==kwargs-dict (not the name).
        data_calls = [c for c in rec.call_args_list if c.args[1] == "data.received"]
        assert len(data_calls) == 1
        assert data_calls[0].args[2] == ["model: Flipper Zero", "channel: RELEASE"]
