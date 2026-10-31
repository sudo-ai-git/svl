"""Wire protocols: how the GUI encodes commands and decodes replies.

Two concrete protocols ship here:

* ``TextProtocol`` -- newline-separated UTF-8 command + response lines. This
  is the working wire contract already captured in ``base.py`` and is the
  default protocol for every transport (backwards compatible).

* ``JsonRpcProtocol`` -- JSON-RPC-2.0 style ``{"content": {...}}`` machine
  readable CLI output, the envelope used by ``flipper-hero/cli`` and the
  official ``flipper raw '{"content": {...}}'`` RPC.  This is a *compile time
  bridge*: the Flipper firmware does not yet speak it at this host, so
  ``encode`` raises until that support lands. It is provided so the protocol
  path is modelled, unit-tested, and ready to flip on when firmware is
  updated.

Protocols are deliberately transactional: one command -> one reply.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .base import Transport


__all__ = ["ProtocolABC", "TextProtocol", "JsonRpcProtocol"]

if TYPE_CHECKING:
    TransportT = Transport
else:
    TransportT = object


class ProtocolABC(ABC):
    """One protocol. One command -> one reply."""

    @abstractmethod
    def encode(self, name: str, args: list[str] | None) -> bytes:
        """Turn a command name + args into wire bytes."""

    @abstractmethod
    def decode(self, data: bytes) -> list[str]:
        """Turn raw reply bytes into a list of stripped, non-empty lines."""

    def call(self, transport: TransportT, name: str, args: list[str] | None,
             timeout: float = 3.0) -> list[str]:
        """Send a command, read the complete reply, return the lines."""
        transport.send(self.encode(name, args))
        return self.decode(self._read_bytes(transport, timeout))

    def _read_bytes(self, transport: TransportT, timeout: float) -> bytes:
        """Stability-guarded bounded read; mirrors :meth:`Device._read_response`."""
        import time
        deadline = time.monotonic() + timeout
        buf = b""
        last_data = 0.0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            chunk = transport.receive(timeout=min(0.05, remaining))
            if chunk:
                buf += chunk
                last_data = time.monotonic()
            if buf and (time.monotonic() - last_data) > 0.35:
                break
        return buf


class TextProtocol(ProtocolABC):
    """Newline-separated UTF-8 text protocol (the default).

    Matches the contract in ``comm/base.py`` and the existing transport
    behaviour, so existing device backends keep working unchanged.
    """

    def encode(self, name: str, args: list[str] | None) -> bytes:
        line = name
        if args:
            line += " " + " ".join(str(a) for a in args)
        return (line + "\n").encode("utf-8", errors="replace")

    def decode(self, data: bytes) -> list[str]:
        return [ln.strip() for ln in data.decode("utf-8", errors="replace").splitlines() if ln.strip()]


class JsonRpcProtocol(ProtocolABC):
    """JSON-RPC-2.0 style machine readable CLI bridge.

    Envelope::

        {"jsonrpc": "2.0", "method": "flipper.raw.set_output", "params": {...}}

    The Flipper firmware does not yet implement this shape at this host, so
    ``encode`` raises :class:`NotImplementedError` until that support is
    merged. This keeps the protocol path unit-tested and ready to flip on.
    """

    USER_AGENT = "flipper-gui/0.1.0 (JSON-RPC bridge)"

    def encode(self, name: str, args: list[str] | None) -> bytes:
        raise NotImplementedError(
            "JsonRpcProtocol is a compile-time bridge: the Flipper firmware "
            "does not speak JSON-RPC yet at this host. Add the method + params "
            "support, then re-enable this."
        )

    def decode(self, data: bytes) -> list[str]:
        raise NotImplementedError(
            "JsonRpcProtocol is a compile-time bridge: the Flipper firmware "
            "does not speak JSON-RPC yet at this host. Re-enable once it does."
        )
