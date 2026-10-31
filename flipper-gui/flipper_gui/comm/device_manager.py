"""Device discovery + selection, then connection, for the Flipper GUI.

This module is the "connect" layer: it finds candidate Flipper devices
(serial HID/CDC, Bluetooth LE, plus a process/USB inventory) and hands a
chosen candidate to a :class:`Transport` so the GUI can connect it.

Design notes
------------
* Discovery is deliberately **platform-aware** and intentionally lazy for
  Bluetooth (``bleak`` is only imported on demand) so the package imports on
  a headless box without a BT controller.
* The GUI does *not* talk to transports directly; it asks for candidates and
  receives (transport, path, kind), keeping the transport layer swappable.
"""

from __future__ import annotations

import glob
import os
import sys

from .base import Transport

__all__ = ["DeviceCandidate", "DeviceManager", "CandidateKind"]

_FALLBACK_BAUDS = (9600, 115200, 230400, 460800, 921600)


class CandidateKind(str):
    SERIAL = "serial"
    BLE = "ble"
    RF = "rf"
    UNKNOWN = "unknown"


class DeviceCandidate:
    """A single discoverable Flipper candidate."""

    def __init__(self, name: str, kind: str, path: str = "", note: str = ""):
        self.name = name
        self.kind = kind
        self.path = path
        self.note = note

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "path": self.path, "note": self.note}


class DeviceManager:
    """Discovers Flipper candidates and connects one against a transport."""

    def __init__(self, registry=None) -> None:
        self.registry = registry  # e.g. CommandRegistry, optional

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    def discover(self) -> list[DeviceCandidate]:
        """Enumerate candidate Flipper devices across the serial and BLE."""
        cands: list[DeviceCandidate] = []
        cands.extend(self._serial_candidates())
        try:
            cands.extend(self._ble_candidates())
        except Exception:  # noqa: BLE001
            # Bluetooth tooling is missing / the host has no BT controller;
            # graceful, not fatal.
            pass
        cands.append(DeviceCandidate(kind=CandidateKind.RF,
                                     name="RF controller (CC1101)")
        )
        return cands

    def _serial_candidates(self) -> list[DeviceCandidate]:
        cands: list[DeviceCandidate] = []

        def add(path: str, kind: str, note: str = "") -> None:
            if path and path not in [c.path for c in cands]:
                cands.append(DeviceCandidate(name=path, kind=kind, path=path, note=note))

        # Linux CDC/HID serial (raw devices).
        for pat in ("/dev/ttyACM*", "/dev/ttyUSB*", "/dev/ttyS*"):
            for path in sorted(glob.glob(pat)):
                add(path, CandidateKind.SERIAL, f"{pat} device")

        # device symlinks (/dev/serial/by-id, /dev/serial/by-path).
        for base in ("/dev/serial", "/dev/usb", "/dev/icm"):
            for pat in (f"{base}/by-id/*", f"{base}/by-path/*"):
                try:
                    for path in glob.glob(pat):
                        if os.path.exists(path):
                            add(path, CandidateKind.SERIAL, f"symlink {pat}")
                except OSError:
                    pass

        # Windows COM ports.
        if sys.platform.startswith("win"):
            for n in range(1, 33):
                cands.append(DeviceCandidate(path=f"COM{n}",
                                             kind=CandidateKind.SERIAL,
                                             note=f"COM{n} (Windows)"))

        return cands

    def _ble_candidates(self) -> list[DeviceCandidate]:
        try:
            from bleak import BleakScanner  # lazy import so the package loads
        except Exception:
            return []
        try:
            devices = BleakScanner.discover(timeout=4.0)
        except Exception:
            return []
        out = []
        for d in devices:
            low = (d.name or "").lower()
            if any(k in low for k in ("flipper", "caroto", "ble_spam")):
                out.append(DeviceCandidate(name=d.name or "unknown_flipper",
                                           kind=CandidateKind.BLE, path=d.address,
                                           note=f"BLE {d.address}"))
        return out

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def connect(self, candidate: DeviceCandidate,
                factory) -> tuple[Transport | None, str]:
        """Open a transport for *candidate* via *factory*.

        ``factory`` is a callable ``(path: str) -> Transport`` (e.g. an
        instantiated :class:`UsbSerialTransport` or :class:`BleTransport`).
        Returns ``(transport, status_message)``.
        """
        if candidate.kind == CandidateKind.SERIAL:
            return self._connect_serial(candidate, factory)
        if candidate.kind == CandidateKind.BLE:
            return self._connect_ble(candidate, factory)
        if candidate.kind == CandidateKind.RF:
            # RF chooses a specific CC1101 backend; "connected" = backend
            # selected, not a live device.  This keeps the layer swappable.
            t = factory(candidate.path)
            return (t, "RF backend selected (no live device)")
        return None, "unknown candidate kind"

    def _connect_serial(self, candidate, factory) -> tuple[Transport | None, str]:
        transport = factory(candidate.path)
        if transport.connect():
            return transport, "serial opened"
        # Failed on the default baud; retry with a small set of common baud
        # settings for mismatched firmware.
        for baud in _FALLBACK_BAUDS:
            try:
                transport.baud = baud
                if transport.connect():
                    return transport, f"serial opened (baud {baud})"
            except Exception:
                continue
        return None, "serial open failed"

    def _connect_ble(self, candidate, factory) -> tuple[Transport | None, str]:
        t = factory(address=candidate.path)
        if t.connect():
            return t, "BLE client connected"
        return None, f"BLE connect to {candidate.path} failed"
