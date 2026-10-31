"""Session: holds a Device, its Transport, and its registry, and exposes
the request/reply path. No background thread — a tab's ``request`` does a
bounded send + read, so one command does not share the wire with another.

To keep things testable and honest, the event-bus machinery lives here only
as a thin binding: the Device emits ``data.received`` (via its events
callback) when a reply arrives, and the UI subscribes to those events.
"""

from __future__ import annotations

from typing import Callable, Iterable, TYPE_CHECKING

from .base import Transport
from .usb_serial import UsbSerialTransport

if TYPE_CHECKING:
    from .devices import Device  # noqa: F401

__all__ = ["Session"]


class Session:
    """Thin binding between a :class:`Device` and a :class:`Transport`.

    Construct with a (device, transport, registry). Every feature tab issues
    commands through :meth:`request` and receives results on the device's
    event loop.

    Attributes:
        device: the logical device (model + registry + event callback).
        transport: the wire backend implementing :class:`Transport`.
        registry: the command registry; defaults to the device's own.
    """

    def __init__(self, device: "Device", transport: Transport, registry: object | None = None) -> None:
        self.device = device
        self.device.registry = registry or device.registry
        self.transport = transport

    # -------------------------------------------------------------- #
    # Request / reply
    # -------------------------------------------------------------- #
    def request(self, name: str, args: list[str] | None = None, timeout: float = 3.0) -> list[str]:
        """Equivalent to :meth:`Device.request` against this session's device."""
        return self.device.request(name, args=args, timeout=timeout)

    @property
    def device_type(self) -> str:
        return self.device.device_type if self.device is not None else "none"

    @property
    def connected(self) -> bool:
        return self.device.is_connected() if self.device is not None else False
