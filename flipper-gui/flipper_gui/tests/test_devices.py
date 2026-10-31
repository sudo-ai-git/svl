"""Tests for the core device model and the command registry."""

from __future__ import annotations

import pytest
import sys
from unittest import mock

from flipper_gui.core.commands import Command
from flipper_gui.core.devices import Device, DeviceInfo, DeviceType, Capability
from flipper_gui.comm.base import Transport
from flipper_gui.core.registry import CommandRegistry


class DummyTransport(Transport):
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
        data_calls = [c for c in rec.call_args_list if c.args[1] == "data.received"]
        assert len(data_calls) == 1

    def test_capability_available_only_when_enabled_and_connected(self) -> None:
        tx = DummyTransport()
        dev = Device(device_type=DeviceType.USB_SERIAL, transport=tx)
        cap = Capability(name="nfc", enabled=True)
        assert cap.is_available(dev) is False
        dev.connect()
        assert cap.is_available(dev) is True
        dev.disconnect()
        assert cap.is_available(dev) is False

    def test_capability_guard_none_device(self) -> None:
        cap = Capability(name="nfc", enabled=True)
        assert cap.is_available(None) is False

    def test_enable_feature_toggle_and_persist(self) -> None:
        dev = Device(device_type=DeviceType.USB_SERIAL)
        tx = DummyTransport()
        dev.transport = tx
        dev.connect()
        cap = Capability(name="nfc", enabled=True)
        dev._capabilities = [cap]
        cap = dev.get_capability("nfc")  # type: ignore[reportAttributeAccessIssue]
        assert cap is not None
        assert cap.enabled is True
        assert cap.is_available(dev) is True

        dev.enable_feature("nfc", enabled=False)
        cap = dev.get_capability("nfc")
        assert cap is not None
        assert cap.enabled is False
        assert cap.is_available(dev) is False

        dev.enable_feature("nfc", enabled=True)
        cap = dev.get_capability("nfc")
        assert cap is not None
        assert cap.enabled is True
        assert cap.is_available(dev) is True

    def test_get_capability_on_fresh_device_returns_none(self) -> None:
        dev = Device(device_type=DeviceType.USB_SERIAL)
        # No capabilities set yet -> none (must not raise AttributeError).
        assert dev.get_capability("nfc") is None

    def test_enable_feature_on_fresh_device_creates(self) -> None:
        dev = Device(device_type=DeviceType.USB_SERIAL)
        dev.enable_feature("nfc", True)
        cap = dev.get_capability("nfc")
        assert cap is not None
        assert cap.enabled is True
        # Persisted store now exists.
        assert dev._capabilities is not None
        assert len(dev._capabilities) == 1

    def test_capability_available_malformed_device_returns_false(self) -> None:
        # A non-Device object without an is_connected() contract must never
        # raise AttributeError -- it returns False instead.
        class _NoConnect:
            enabled = True

            def is_connected(self) -> bool:
                return False

        cap = Capability(name="nfc", enabled=True)
        # type: ignore[reportArgumentType]  # deliberate duck-typed probe: miswired call site
        assert cap.is_available(_NoConnect()) is False  # type: ignore[reportArgumentType]  # deliberate duck-typed probe: miswired call site

    def test_capability_available_none_device_returns_false(self) -> None:
        assert Capability(name="nfc").is_available(None) is False

    def test_capability_available_disconnected_device_returns_false(self) -> None:
        dev = Device(device_type=DeviceType.USB_SERIAL)
        assert Capability(name="nfc", enabled=True).is_available(dev) is False
