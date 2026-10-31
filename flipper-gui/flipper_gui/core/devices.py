"""Core domain: devices, capabilities, and the command registry.

Pure domain only — no Qt, no transport. It imports :class:`Command` from
``.commands`` and keeps the cross-module ``CommandRegistry`` reference as a
forward-declared string so there is no circular import.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable

from .commands import Command


class DeviceType(str, Enum):
    USB_SERIAL = "usb_serial"
    BLE = "ble"
    RF = "rf"


@dataclass
class DeviceInfo:
    model: str = "Flipper Zero"
    firmware_channel: str = "RELEASE"
    region: str = ""
    battery_percent: int = 100
    battery_voltage: float = 0.0
    transport_type: str = ""
    transport_path: str = ""
    connected: bool = False
    uptime_s: int = 0
    device_type: str = "flipper_zero"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Device:
    """Logical device the GUI talks to: a transport + capability set + registry."""

    device_type: DeviceType
    transport: object | None = None
    info: DeviceInfo = field(default_factory=DeviceInfo)
    registry: object | None = None
    events: Callable[[object, str, object], None] | None = None

    def connect(self) -> bool:
        if self.transport is None:
            return False
        ok = self.transport.connect()
        if ok:
            self.info.connected = True
            self.emit("device.connected", self.info.to_dict())
        return ok

    def disconnect(self) -> None:
        if self.transport is not None:
            self.transport.disconnect()
        self.info.connected = False
        self.emit("device.disconnected", None)

    def command(self, name: str, args: list[str] | None = None) -> list[str] | None:
        reg = getattr(self, "registry", None)
        if reg is None or reg.get(name) is None or not self.is_connected():
            return None
        return reg.get(name).execute(self, args or [])

    def is_connected(self) -> bool:
        return self.info.connected

    def emit(self, event: str, payload: object) -> None:
        events = getattr(self, "events", None)
        if events is not None:
            try:
                events(self, event, payload)
            except Exception:
                pass

    def set_events(self, events: Callable[[object, str, object], None] | None) -> None:
        self.events = events


@dataclass
class Capability:
    name: str
    enabled: bool = True
    description: str = ""

    def is_available(self, device: Device) -> bool:
        return self.enabled and bool(device.is_connected())
