""""""

from __future__ import annotations

import os
from PySide6 import QtWidgets


class DeviceInfoTab(QtWidgets.QWidget):
    """Device info tab: shows model, firmware channel, region, battery."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Device info")
        self._build_layout()

    def _build_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QtWidgets.QLabel("Device info")
        header.setStyleSheet("font-weight: 700; font-size: 18px;")

        self.model_label = QtWidgets.QLabel("—")
        self.channel_label = QtWidgets.QLabel("—")
        self.region_label = QtWidgets.QLabel("—")
        self.battery_label = QtWidgets.QLabel("—")

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Model"), 0, 0)
        grid.addWidget(self.model_label, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Firmware channel"), 1, 0)
        grid.addWidget(self.channel_label, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Region"), 2, 0)
        grid.addWidget(self.region_label, 2, 1)
        grid.addWidget(QtWidgets.QLabel("Battery"), 3, 0)
        grid.addWidget(self.battery_label, 3, 1)

        layout.addWidget(header)
        layout.addLayout(grid)
        layout.addWidget(QtWidgets.QLabel("(placeholder tab — connects on Phase 4)"))

    def refresh(self) -> None:
        """Placeholder: populated when a device is connected."""
        self.model_label.setText("Flipper Zero")
        self.channel_label.setText("RELEASE")
        self.region_label.setText("")
        self.battery_label.setText("100%")
