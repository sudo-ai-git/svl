"""Core domain: devices, capabilities, and the command registry.

Pure domain only — no Qt, no transport. It imports :class:`Command` from
``.commands`` and keeps the cross-module ``CommandRegistry`` reference as a
forward-declared string so there is no circular import.

Layout:
  devices.Device       logical device (model + transport + command registry)
  devices.DeviceInfo   device info model (model, channel, region, battery...)
  commands.Command     versioned command schema + timeout
  registry.CommandRegistry  command lookup + discovery
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, Iterable, TYPE_CHECKING
import time

from .commands import Command
from ..comm.protocol import ProtocolABC, TextProtocol
from ..comm.base import Transport

if TYPE_CHECKING:
    from .registry import CommandRegistry


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
    """Logical device the GUI talks to: a transport + command registry.

    Wire protocol (see ``comm/base.py``): newline-separated UTF-8 command
    and response lines. The single blocking entry point is :meth:`request`,
    which *send the command, read the reply, return the lines.* That is
    what every feature tab uses.
    """

    device_type: DeviceType
    transport: Transport | None = None
    info: DeviceInfo = field(default_factory=DeviceInfo)
    registry: "CommandRegistry | None" = None
    events: Callable[[object, str, object], None] | None = None
    protocol: ProtocolABC = field(default_factory=TextProtocol)

    # -------------------------------------------------------------- #
    # Connection
    # -------------------------------------------------------------- #
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

    def is_connected(self) -> bool:
        return self.info.connected

    # -------------------------------------------------------------- #
    # Commands / replies
    # -------------------------------------------------------------- #
    def request(self, name: str, args: list[str] | None = None,
                timeout: float = 3.0) -> list[str]:
        """Send a command and read the full reply (blocking, bounded).

        Builds the wire line from the command name + args, pushes it over the
        transport, then reads (with a stability guard) until the reply has
        settled. Returns the non-empty response lines. Returns ``[]`` when
        the command, transport, or device is missing/ disconnected.
        """
        reg = getattr(self, "registry", None)
        if reg is None:
            return []
        cmd = reg.get(name)
        if cmd is None or not self.is_connected():
            return []
        transport = self.transport
        if transport is None:
            return []

        reply = self.protocol.call(transport, name, args, timeout)
        # Deliver the reply on the event bus so feature tabs observe it
        # (device_info / live tabs subscribe here). The emit is best-effort:
        # a missing/emit-cost tolerance never blocks the wire reply.
        self.emit("data.received", reply)
        return reply

    def status_snapshot(self) -> dict:
        """Return a JSON-serialisable view of this device's live state.

        Intentionally omits :attr:`transport` and :attr:`protocol` so the
        snapshot is safe to send over the wire or log.
        """
        capabilities = [c.name for c in self.capabilities()]

        device_type = self.device_type
        if isinstance(device_type, DeviceType):
            device_type = device_type.value

        return {
            "device_type": device_type,
            "model": self.info.model,
            "firmware_channel": self.info.firmware_channel,
            "region": self.info.region,
            "battery_percent": self.info.battery_percent,
            "battery_voltage": self.info.battery_voltage,
            "transport_type": self.info.transport_type,
            "transport_path": self.info.transport_path,
            "connected": self.info.connected,
            "uptime_s": self.info.uptime_s,
            "device_category": self.info.device_type,
            "capabilities": capabilities,
        }

    def emit(self, event: str, payload: object) -> None:
        events = getattr(self, "events", None)
        if events is not None:
            try:
                events(self, event, payload)
            except Exception:
                pass

    def set_events(self, events: Callable[[object, str, object], None] | None) -> None:
        self.events = events

    # -------------------------------------------------------------- #
    # -------------------------------------------------------------- #
    # -------------------------------------------------------------- #
    # Capability introspection (used by some tabs)
    # -------------------------------------------------------------- #
    def capabilities(self) -> list["Capability"]:
        """Return this device's live feature set.

        Capabilities combine explicit toggles the UI persists with command-
        derived capabilities discovered from the connected device's registry
        -- the features the device actually speaks on the wire. Duplicate names
        are merged, so the returned list is clean.
        """
        caps = [c for c in getattr(self, "_capabilities", []) if c.enabled]
        if self.registry is not None:
            seen = {c.name for c in caps}
            for cmd_name in self.registry.list_commands():
                if cmd_name in seen:
                    continue
                cmd = self.registry.get(cmd_name)
                caps.append(Capability(
                    name=cmd_name,
                    description=cmd.description if cmd else "",
                    enabled=True,
                ))
                seen.add(cmd_name)
        return caps

    def set_capabilities(self, capabilities: Iterable["Capability"]) -> None:
        """Persist the preferred capability set (feature enable/disable state).

        The UI's source of truth for which features a user wants enabled.
        A live device takes precedence over an explicit set.
        """
        self._capabilities = list(capabilities)

    def get_capability(self, name: str) -> "Capability | None":
        """Return the capability named *name*, searching the persistent store.

        Note: the UI-visible :meth:`capabilities` view filters out disabled
        entries, so this lookup uses the raw persisted list so a disabled
        feature can still be retrieved and re-enabled.
        """
        for c in self._capabilities:
            if c.name == name:
                return c
        return None

    def enable_feature(self, name: str, enabled: bool = True) -> None:
        """Toggle a capability on or off; add it if not present.

        Works against the raw persisted list, so a previously disabled
        feature can be re-enabled without being duplicated.
        """
        for c in self._capabilities:
            if c.name == name:
                c.enabled = enabled
                return
        desc = ""
        if self.registry is not None:
            cmd = self.registry.get(name)
            if cmd is not None:
                desc = cmd.description
        self._capabilities.append(
            Capability(name=name, enabled=enabled, description=desc)
        )


@dataclass
class Capability:
    """A named, enabled, documented feature capability the device exposes."""

    name: str
    enabled: bool = True
    description: str = ""

    def is_available(self, device: "Device") -> bool:
        """Return True if this capability is available on *device*.

        A capability is only actionable when it is enabled AND the
        underlying device is connected; ``device=None`` (no live device)
        is always treated as unavailable so the UI/tabs never crash.
        """
        if device is None:
            return False
        return self.enabled and bool(device.is_connected())
