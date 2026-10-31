"""BLE (GATT) transport over the Flipper's Bluetooth LE radio.

Uses the ``bleak`` library. The Flipper exposes a BLE service for pairing
and data; this backend wires to it. Requires OS-level Bluetooth on the host.

Connect requires ``ble_address`` (the Flipper's BLE address) to be set in
settings; on Linux Bluetooth permissions can be granted via udev rules or by
unlocking the system Bluetooth stack.

Note: the ``bleak`` import is deferred to connect-time so the ``flipper_gui``
package imports cleanly even when BLE is not installed.
"""

from __future__ import annotations

from typing import Callable

from .base import Transport

# Service / characteristic negotiated by the Flipper's BLE backend (Flipper
# Mobile App style). These are placeholders — verify against the device.
_DEFAULT_SERVICE = "19B10000-E8F2-537E-4F6C-DCA860E35C88"
_DEFAULT_CHAR_TX = "19B10001-E8F2-537E-4F6C-DCA860E35C88"
_DEFAULT_CHAR_RX = "19B10002-E8F2-537E-4F6C-DCA860E35C88"


class BleTransport(Transport):
    """BLE GATT transport for communicating with the Flipper."""

    def __init__(self, address: str = "", service: str = _DEFAULT_SERVICE,
                 char_tx: str = _DEFAULT_CHAR_TX, char_rx: str = _DEFAULT_CHAR_RX,
                 timeout: float = 1.0) -> None:
        self.address = address
        self.service = service
        self.char_tx = char_tx
        self.char_rx = char_rx
        self.timeout = timeout
        self._client = None
        self._emitter: Callable[[Transport, str, object], None] | None = None

    # ------------------------------------------------------------------ #
    # Transport interface
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        if not self.address:
            return False
        try:
            from bleak import BleakClient  # lazy import so the package loads
            self._client = BleakClient(self.address, timeout=self.timeout)
            self._client.connect()
            return True
        except Exception as exc:  # noqa: BLE001
            self._client = None
            self._emitter and self._emitter(self, "error", f"BLE connect failed: {exc}")
            return False

    def disconnect(self) -> None:
        if self._client is not None and self._client.is_connected:
            try:
                self._client.disconnect()
            except Exception:
                pass
        self._client = None

    def send(self, data: bytes) -> bool:
        if self._client is None or not self._client.is_connected:
            return False
        try:
            from bleak import BleakClient  # noqa: F401
            self._client.write_gatt_char(self.char_tx, data, response=False)
            return True
        except Exception:
            return False

    def receive(self) -> bytes | None:
        # BLE notification/characteristic reads are async; override for blocking
        # reads if your device exposes one. Here we return None unless a
        # pending notification arrived (backend-dependent).
        if self._client is None or not self._client.is_connected:
            return None
        # Attempt a read of the RX characteristic if the device supports it.
        try:
            # Read once; a full implementation may use notify/subscribe.
            from bleak import BleakClient  # noqa: F401
            return self._client.read_gatt_char(self.char_rx)
        except Exception:
            return None

    def on_event(self, emitter: Callable[[Transport, str, object], None]) -> None:
        self._emitter = emitter

    def command(self, name: str, args: list[str] | None = None, payload: object | None = None) -> list[str] | None:
        return None
