"""Transport abstraction: every transport the GUI talks to the Flipper with
implements this interface. The rest of the app (device model, UI) depends only
on this, never on any single backend.
"""

from __future__ import annotations

from typing import Callable, Awaitable

EventEmitter = Callable[["Transport", str, object], None]


class Transport:
    """Base for USB-serial, BLE, and RF backends."""

    def connect(self) -> bool:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def send(self, data: bytes) -> bool:
        raise NotImplementedError

    def receive(self) -> bytes | None:
        raise NotImplementedError

    def on_event(self, emitter: EventEmitter) -> None:
        """Register a callback fired on bus events (e.g. device.connected)."""

    def command(self, name: str, args: list[str] | None = None, payload: object | None = None) -> list[str] | None:
        """Versioned command; default: not supported by wire protocol."""

    def close(self) -> None:
        self.disconnect()
