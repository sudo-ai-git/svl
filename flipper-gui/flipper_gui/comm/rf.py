"""Sub-1 GHz radio transport seam.

The Flipper's radio is a CC1101 (seen on Sub-GHz modules and devboards).
This transport is the seam where an RF backend is injected:

  * *Fast path:* a small C/C++/asm extension built with cython or cffi,
    exposing ``open()/close()/write()/read()/set_frequency(int)``.
  * *Prototype path:* a stub that logs the command so the rest of the app is
    shippable before any RF hardware is attached.

Wire-agnostic: the GUI only sees ``send()``/``receive()``.
"""

from __future__ import annotations

from typing import Callable

from .base import Transport

# Default carrier parameters (used by the stub prototype path).
_DEFAULT_FREQUENCY_HZ = 433920000
_DEFAULT_MODULATION = "fm"


class RFTxTransport(Transport):
    """Sub-1 GHz radio transport.

    The default implementation is a logging stub so the rest of the GUI
    builds and ships before hardware is attached. Hardware users override
    ``send``/``receive`` with their own backend.
    """

    def __init__(self, *, frequency_hz: int = _DEFAULT_FREQUENCY_HZ,
                 modulation: str = _DEFAULT_MODULATION) -> None:
        self.frequency_hz = frequency_hz
        self.modulation = modulation
        self._emitter = None

    # ------------------------------------------------------------------ #
    # Transport interface
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        self._emitter and self._emitter(self, "info", "rf.stub: open (prototype path)")
        return True

    def disconnect(self) -> None:
        self._emitter and self._emitter(self, "info", "rf.stub: close")

    def send(self, data: bytes) -> bool:
        self._emitter and self._emitter(self, "rf.send", {"bytes": len(data), "freq": self.frequency_hz})
        return True

    def receive(self) -> bytes | None:
        # Stub: returns None until an RF backend is wired in. The Storage/UI
        # tier can poll; producers should instead push via on_event().
        return None

    def on_event(self, emitter: Callable[[Transport, str, object], None]) -> None:
        self._emitter = emitter

    def command(self, name: str, args: list[str] | None = None, payload: object | None = None) -> list[str] | None:
        return None
