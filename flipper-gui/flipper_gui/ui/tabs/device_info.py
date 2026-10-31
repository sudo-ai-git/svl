"""Device info tab: shows live model, firmware channel, region, battery.

This tab is populated from the connected :class:`Device` and refreshes when
the device connects or its capabilities change.
"""

from __future__ import annotations

from typing import Optional

from PySide6 import QtWidgets

from ...core.devices import Device

__all__ = ["DeviceInfoTab"]


class DeviceInfoTab(QtWidgets.QWidget):
    """Live device info: model, firmware channel, region, battery."""

    def __init__(self, parent: QtWidgets.QWidget | None = None,
                 device: "Device" | None = None) -> None:
        super().__init__(parent)
        self.device: "Device | None" = device
        self._build_layout()
        self.refresh()

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

    def device(self) -> "Device | None":
        return self._device

    def set_device(self, device: "Device | None") -> None:
        self._device = device
        self.refresh()

    def refresh(self) -> None:
        d = self._device
        if d is None or not d.is_connected():
            self.model_label.setText("—")
            self.channel_label.setText("—")
            self.region_label.setText("—")
            self.battery_label.setText("—")
            return

        info = d.info
        self.model_label.setText(info.model or "—")
        self.channel_label.setText(info.firmware_channel or "—")
        self.region_label.setText(info.region or "—")
        self.battery_label.setText(f"{info.battery_percent}%")
