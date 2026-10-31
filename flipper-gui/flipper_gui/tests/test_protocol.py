"""Tests for the cutting-edge comm layer: wire protocols (A1), baud
auto-detection (A3), and the connection state / status model (A5)."""

from __future__ import annotations

import sys
import types
import json
import pytest
from unittest import mock

# Inject a fake `serial` module so pyserial imports succeed in a headless box.
_t = types.ModuleType("serial")


class _FakeSerial:
    """Pluggable serial backend used for unit tests only."""

    def __init__(self, *args, **kwargs):
        self.args = args

    def close(self) -> None:
        pass

    @property
    def in_waiting(self) -> int:
        return 0

    def read(self, n: int = 0) -> bytes:
        return b""

    def write(self, data: bytes) -> None:
        pass

    @property
    def is_open(self) -> bool:
        return True


_t.Serial = _FakeSerial
sys.modules.setdefault("serial", _t)

# Import the concrete protocols under test.
from flipper_gui.comm.protocol import JsonRpcProtocol, TextProtocol  # noqa: E402
from flipper_gui.comm.usb_serial import UsbSerialTransport  # noqa: E402
import flipper_gui.comm.usb_serial as _usb_serial  # noqa: E402
from flipper_gui.core.devices import Device, DeviceInfo, DeviceType  # noqa: E402


class _MockTransport:
    """Transport whose receive() streams canned lines."""

    def __init__(self, path: str = "/dev/ttyS0", baud: int = 115200) -> None:
        self.path = path
        self.baud = baud
        self._port = None
        self._tx = b""
        self._rx_lines: list[bytes] = []

    def connect(self) -> bool:
        self._port = object()
        return True

    def disconnect(self) -> None:
        self._port = None

    def send(self, data: bytes) -> bool:
        self._tx = data
        return True

    def receive(self, timeout: float = 0.05) -> bytes:
        # Deliver the queued line exactly once, then go quiet so the
        # protocol's idle-guard settles the reply (see issue #1).
        if self._rx_lines:
            return self._rx_lines.pop(0)
        return b""

    def set_rx(self, line: str) -> None:
        self._rx_lines.append(line.encode("utf-8"))


class TestTextProtocol:
    def test_encode_builds_line(self) -> None:
        p = TextProtocol()
        assert p.encode("fw", None) == b"fw\n"
        assert p.encode("fw", ["433920000"]) == b"fw 433920000\n"
        assert p.encode("fw", ["a", "b"]) == b"fw a b\n"

    def test_decode_returns_lines(self) -> None:
        p = TextProtocol()
        assert p.decode(b"") == []
        assert p.decode(b"  \n   ") == []
        assert p.decode(b"model: Flipper Zero\nchannel: RELEASE\n") == [
            "model: Flipper Zero",
            "channel: RELEASE",
        ]

    def test_encode_decodes_roundtrip(self) -> None:
        p = TextProtocol()
        assert p.decode(p.encode("fw", ["433920000"])) == ["fw 433920000"]

    def test_call_wires_send_and_read(self) -> None:
        p = TextProtocol()
        t = _MockTransport()
        t.set_rx("model: Flipper Zero")
        out = p.call(t, "fw", ["433920000"], timeout=0.5)
        assert out == ["model: Flipper Zero"]
        assert t._tx == b"fw 433920000\n"


class TestJsonRpcProtocol:
    """Compile-time bridge: the Flipper firmware does not yet speak JSON-RPC."""

    def test_encode_raises_requires_firmware(self) -> None:
        p = JsonRpcProtocol()
        with pytest.raises(NotImplementedError):
            p.encode("fw", None)

    def test_decode_raises_requires_firmware(self) -> None:
        p = JsonRpcProtocol()
        with pytest.raises(NotImplementedError):
            p.decode(b"{}")


class TestBaudDetection:
    def test_baud_candidates_start_with_9600(self) -> None:
        # Candidate list is ordered slow-to-fast. 9600 is the safest first.
        from flipper_gui.comm.usb_serial import _BAUD_CANDIDATES
        assert _BAUD_CANDIDATES[0] == 9600

    def test_try_baud_returns_first_opening_baud(self) -> None:
        # Deterministic: patch the serial backend so the first candidate baud
        # opens, then assert (True, 9600).
        with mock.patch.object(_usb_serial, "serial", autospec=False) as m:
            class _OpeningSerial:
                def __init__(self, *a, **k):
                    self.arg1 = a[1] if len(a) > 1 else None
                def close(self) -> None:
                    pass
            m.Serial = _OpeningSerial
            ok, baud = UsbSerialTransport._try_baud("/dev/none")
            assert ok is True
            assert baud == 9600

    def test_fallback_when_no_serial_opens(self) -> None:
        # Simulate a serial port that refuses to open; every baud must fail
        # and the fallback must return the configured default baud.
        with mock.patch.object(_usb_serial, "serial", autospec=False) as m:
            class _FailingSerial:
                def __init__(self, *a, **k):
                    raise OSError("no device")
                def close(self) -> None:
                    pass
            m.Serial = _FailingSerial
            m.SerialException = OSError
            ok, baud = UsbSerialTransport._try_baud("/nope")
            assert not ok
            assert baud == 115200

class TestDeviceStatus:
    def test_status_snapshot_is_json_serialisable(self) -> None:
        dev = Device(
            device_type=DeviceType.USB_SERIAL,
            info=DeviceInfo(model="Flipper Zero", firmware_channel="RELEASE",
                            region="EU", battery_percent=87,
                            battery_voltage=3.82, transport_type="usb_serial",
                            transport_path="/dev/ttyACM0", connected=True,
                            uptime_s=3600, device_type="flipper_zero"),
            protocol=TextProtocol(),
        )
        d = dev.status_snapshot()
        assert isinstance(d, dict)
        assert d["model"] == "Flipper Zero"
        assert d["connected"] is True
        assert d["device_category"] == "flipper_zero"
        assert d["capabilities"] == []
        json.dumps(d)  # raises if not serialisable

    def test_status_snapshot_excludes_sensitive_fields(self) -> None:
        dev = Device(
            device_type=DeviceType.USB_SERIAL,
            info=DeviceInfo(model="Flipper Zero", firmware_channel="RELEASE",
                            region="EU", battery_percent=50,
                            battery_voltage=3.6, transport_type="usb_serial",
                            transport_path="/dev/ttyACM0", connected=False,
                            uptime_s=120, device_type="flipper_zero"),
            protocol=TextProtocol(),
        )
        d = dev.status_snapshot()
        assert "transport" not in d
        assert "protocol" not in d
        assert d["connected"] is False
