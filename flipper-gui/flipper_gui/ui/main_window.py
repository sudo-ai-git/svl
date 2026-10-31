"""Main window: status bar, device-list, and tab controller.

The window owns the root ``QApplication`` entry point contract: a menu bar,
a tab widget, and a status bar that reflects the current device state.
"""

from __future__ import annotations

from PySide6 import QtWidgets

from .widgets import DeviceListWidget, StatusBadge
from .tabs import DeviceInfoTab

__all__ = ["MainWindow"]


class MainWindow(QtWidgets.QMainWindow):
    """Root window of the GUI."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Flipper GUI")
        self.resize(960, 620)

        self.tab_widget = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # Device list panel (unified snake-case slot).
        device_panel = DeviceListWidget()
        self.status_badge = StatusBadge()
        self.menu_bar = self.menuBar()

        self._build_menu()
        self._build_layout(device_panel)
        self._build_tabs()
        self._update_badge(device_panel)

    # -------------------------------------------------------------- #
    # Layout
    # -------------------------------------------------------------- #
    def _build_menu(self) -> None:
        file_menu = self.menu_bar.addMenu("&File")
        quit_action = file_menu.addAction("&Quit")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

    def _build_layout(self, device_panel: "DeviceListWidget") -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        control_row = QtWidgets.QHBoxLayout()
        control_row.addWidget(DeviceListWidget())
        control_row.addWidget(self.status_badge)
        layout.addLayout(control_row)

        layout.addWidget(self.tab_widget)

    def _build_tabs(self) -> None:
        tab_widget = self.tab_widget
        tab_widget.addTab(DeviceInfoTab(), "Device info")

    def _update_badge(self, device_panel: "DeviceListWidget") -> None:
        self.status_badge.set_type("info")
        self.status_badge.setText("Idle")

    def connect_device(self) -> None:
        self.status_badge.set_type("info")
        self.status_badge.setText("Connecting...")

    def disconnect_device(self) -> None:
        self.status_badge.set_type("warn")
        self.status_badge.setText("Disconnected")
