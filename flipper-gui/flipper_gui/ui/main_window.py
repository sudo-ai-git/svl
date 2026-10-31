"""Main window: status bar, device list, connect flow, and tab controller.

The window owns the root ``QApplication`` entry point contract.  Its two
responsibilities are:

1. discover (and open) a Flipper device, and
2. own the tab stack that renders it.

Connect is a two-step flow: the menu item / button enumerates candidate
devices (serial + BLE), the user picks one, and the window opens a transport
for it via :class:`DeviceManager`.  The opened transport is wrapped in a
:class:`Device` the tabs talk to.
"""

from __future__ import annotations

from PySide6 import QtWidgets

from .tabs import DeviceInfoTab
from .widgets import StatusBadge, DeviceListWidget
from .comm.device_manager import CandidateKind, DeviceCandidate, DeviceManager
from .comm.usb_serial import UsbSerialTransport
from .comm.ble import BleTransport
from .core.devices import Capability, Device, DeviceType

__all__ = ["MainWindow"]


class MainWindow(QtWidgets.QMainWindow):
    """Root window of the GUI."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Flipper GUI")
        self.resize(960, 620)

        self.manager = DeviceManager()
        self._device: "Device | None" = None
        self._transport = None

        self.tab_widget = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tab_widget)

        self.device_panel = DeviceListWidget()
        self.status_badge = StatusBadge()

        self._build_menu()
        self._build_layout()
        self._build_tabs()
        self._update_badge()

    # -------------------------------------------------------------- #
    # Layout / menu
    # -------------------------------------------------------------- #
    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        dev_menu = self.menuBar().addMenu("&Device")
        self.connect_act = dev_menu.addAction("&Connect Flipper")
        self.disconnect_act = dev_menu.addAction("&Disconnect")
        self.disconnect_act.setEnabled(False)
        self.disconnect_act.triggered.connect(self._on_disconnect)
        self.connect_act.triggered.connect(self._on_connect)

    def _build_layout(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        ctrl = QtWidgets.QHBoxLayout()
        ctrl.addWidget(self.device_panel)
        self._connect_btn = QtWidgets.QPushButton("&Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn = QtWidgets.QPushButton("&Disconnect")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        ctrl.addWidget(self._connect_btn)
        ctrl.addWidget(self._disconnect_btn)
        ctrl.addWidget(self.status_badge)
        layout.addLayout(ctrl)

        layout.addWidget(self.tab_widget)

    def _build_tabs(self) -> None:
        self.tab_widget.addTab(DeviceInfoTab(), "Device info")

    def _update_badge(self) -> None:
        self.status_badge.set_type("info")
        self.status_badge.setText("Idle")

    # -------------------------------------------------------------- #
    # Connect flow
    # -------------------------------------------------------------- #
    def _on_connect(self) -> None:
        self.status_badge.set_type("info")
        self.status_badge.setText("Connecting...")
        self._upload()

    def _upload(self) -> None:
        """Enumerate candidates, fill the device panel, and wire the
        currently selected candidate to a transport.

        Returns True when a transport was opened, False otherwise.
        """
        candidates = self.manager.discover()
        self.device_panel.set_devices(candidates)

        if not candidates:
            self.status_badge.set_type("warn")
            self.status_badge.setText("No Flipper candidates found on this host")
            return False

        cand = self.device_panel.current_candidate()
        if cand is None:
            self.status_badge.set_type("warn")
            self.status_badge.setText("Select a device above, then press Connect")
            return False

        transport, status = self._connect_transport(cand)
        if transport is None:
            self.status_badge.set_type("error")
            self.status_badge.setText(f"Connect failed: {status}")
            return False

        # Each previously-open tab re-registers its commands so the new
        # Device can dispatch them (see :meth:`Device.register_commands`).
        self._commit(transport)
        self._update_disconnect_buttons()
        self.status_badge.set_type("connected")
        self.status_badge.setText(f"Connected: {self._device.info.model}")
        return True

    def _on_disconnect(self) -> None:
        if self._device is not None:
            self._device.disconnect()
            self._device = None
            self._transport = None
        self._update_disconnect_buttons()
        self._set_status("disconnected", "Disconnected")

    def _connect_transport(self, cand) -> tuple:
        factory = _CONNECTORS.get(cand.kind)
        if factory is None:
            if cand.kind == CandidateKind.RF:
                t = self.manager._connect_rf(cand)
                return t, "RF backend selected"
            return None, f"no connector for {cand.kind}"
        return self.manager.connect(cand, lambda: factory(cand.path))

    def _commit(self, transport) -> None:
        self._transport = transport
        self._device = Device(device_type=DeviceType.USB_SERIAL, transport=transport)
        self._device.set_events(self._on_device_event)
        self._device.connect()

    def _on_device_event(self, device, event, payload) -> None:
        if event == "device.connected":
            self._set_status("connected", f"Connected: {payload.get('model', 'unknown')}")

    def _set_status(self, kind: str, text: str) -> None:
        if self.status_badge is None:
            return
        self.status_badge.set_type(kind)
        self.status_badge.setText(text)

    def _update_disconnect_buttons(self) -> None:
        connected = self._device is not None and self._device.is_connected()
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)

    # Shortcuts (public interface) ------------------------------- #
    def connect_device(self) -> None:
        self._upload()

    def disconnect_device(self) -> None:
        self._on_disconnect()


_CONNECTORS = {
    CandidateKind.SERIAL: UsbSerialTransport,
    CandidateKind.BLE: BleTransport,
}
