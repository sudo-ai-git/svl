"""Transport abstraction: every transport the GUI talks to the Flipper with
implements this interface. The rest of the app (device model, UI) depends only
on this, never on any single backend.

Protocol (all transports agree on it):
  * Commands and responses are **newline-separated UTF-8 lines** sent over the
    transport. A command is `name <args...>\n`; a response is zero or more
    `key: value` or bare lines, terminated by the side that sent it.
  * `send(data)` writes bytes.
  * `receive(timeout)` **blocks** until data is available (or `timeout`
    seconds elapse), then returns everything that has arrived. Used by
    `Device.request()` so a command gets its full reply. Do not call this
    from two threads at once.
  * New backends only need `connect/diconnect/send/receive`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable

EventEmitter = Callable[["Transport", str, object], None]


class Transport(ABC):
    """Base for USB-serial, BLE, and RF backends."""

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def send(self, data: bytes) -> bool:
        """Write bytes over the wire. Return True on success."""

    @abstractmethod
    def receive(self, timeout: float = 0.05) -> bytes:
        """Wait up to `timeout` seconds for bytes, then return them (may be
        empty). Intentional consumer of the wire; do not call from two
        threads at once."""

    def close(self) -> None:
        """Release the transport's resources. Concrete transports override
        this; by default it is a no-op."""
        pass
