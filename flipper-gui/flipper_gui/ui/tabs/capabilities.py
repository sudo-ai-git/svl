"""Feature Capabilities tab.

Exposes the connected device's live feature set through :class:`Capability`
with a live readout of ``Capability.is_available(device)``. A capability is
*actionable* only when both its user preference is enabled *and* the device
itself is connected.

Layout:

    Capabilities                                  | Status: connected

    Feature        | Description                  | Enable | Available
    -------------------------------------------------------------------------
    nfc            | 13.56 MHz card emulation     | [x]    | yes
    sub-ghz        | Sub-GHz scanner              | [ ]    | no

The ``Available`` column is derived live from :meth:`Capability.is_available`
and therefore reflects the device's connection state - a capability with an
enabled toggle that is currently disconnected shows as *not available*.

The whole tab re-reads the device's capability set from
:meth:`Device.capabilities` every time the device changes, so no capability
surface is ever hard-coded into this UI.
"""

from __future__ import annotations

from typing import Iterable

from PySide6 import QtCore, QtWidgets

from ...core.devices import Capability, Device

__all__ = ["CapabilityTable", "CapabilitiesTab", "sync_capabilities"]


# --------------------------------------------------------------------------- #
# Presentation widget
# --------------------------------------------------------------------------- #
class CapabilityTable(QtWidgets.QWidget):
    """List of capabilities; edits the enabled state of each."""

    capability_changed = QtCore.Signal(str, bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._device: Device | None = None
        self._rows: dict[str, int] = {}

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(6, 6, 6, 6)

        self._table = QtWidgets.QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ["Capability", "Description", "Enabled", "Available"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setSelectionMode(QtWidgets.QTableWidget.NoSelection)
        self._table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        self._table.setFocusPolicy(QtWidgets.Qt.NoFocus)
        self.layout().addWidget(self._table)

        self._table.itemClicked.connect(self._on_item_clicked)

    # ------------------------------------------------------------------ #
    def set_device(self, device: Device | None) -> None:
        """Attach a live device and refresh the capability list."""
        self._device = device
        if device is None or not device.is_connected():
            self._clear()
        else:
            self._refresh()

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Re-read the capability surface from the attached device."""
        if self._device is None or not self._device.is_connected():
            self._clear()
            return
        self._refresh()

    # ------------------------------------------------------------------ #
    def _clear(self) -> None:
        self._table.clearContents()
        self._table.setRowCount(0)
        self._rows.clear()

    def _refresh(self) -> None:
        caps = self._device.capabilities() if self._device is not None else []
        if self._device is not None and self._device.registry is not None:
            ordered = []
            for cmd_name in self._device.registry.list_commands():
                for cap in caps:
                    if cap.name == cmd_name:
                        ordered.append(cap)
                        break
            for cap in caps:
                if cap.name not in {c.name for c in ordered}:
                    ordered.append(cap)
        else:
            ordered = list(caps)

        self._table.setRowCount(len(ordered))
        self._rows.clear()
        for row, cap in enumerate(ordered):
            self._rows[cap.name] = row

            name_item = QtWidgets.QTableWidgetItem(cap.name)
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
            name_item.setData(QtCore.Qt.UserRole, cap.name)

            desc_item = QtWidgets.QTableWidgetItem(cap.description)
            desc_item.setData(QtCore.Qt.UserRole, "description")

            enabled_item = QtWidgets.QTableWidgetItem("on" if cap.enabled else "off")
            enabled_item.setData(QtCore.Qt.UserRole, "enabled")
            enabled_item.setFlags(
                enabled_item.flags() & ~(QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsUserCheckable)
            )
            enabled_item.setCheckState(QtCore.Qt.Checked if cap.enabled else QtCore.Qt.Unchecked)

            available = cap.is_available(self._device) if self._device is not None else False
            avail_item = QtWidgets.QTableWidgetItem("yes" if available else "no")
            avail_item.setData(QtCore.Qt.UserRole, "available")

            for col, item in enumerate([name_item, desc_item, enabled_item, avail_item]):
                self._table.setItem(row, col, item)

    def _on_item_clicked(self, item: QtWidgets.QTableWidgetItem) -> None:
        if self._device is None or not self._device.is_connected():
            return
        row = self._table.row(item)
        cap = self._device.capabilities()[row]
        new_enabled = not cap.enabled
        self._device.enable_feature(cap.name, new_enabled)
        self.capability_changed.emit(cap.name, new_enabled)
        self.refresh()

    # ------------------------------------------------------------------ #
    def capabilities(self) -> list[Capability]:
        return list(self._rows)  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Tab
# --------------------------------------------------------------------------- #
class CapabilitiesTab(QtWidgets.QWidget):
    """Feature Capabilities tab: advertises everything the device knows how to
    do, its availability and the current enable/disable state of each."""

    def __init__(self, device: Device | None = None, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.device = device
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(10, 10, 10, 10)

        header = QtWidgets.QLabel("Feature Capabilities")
        header.setStyleSheet("font-weight: 700; font-size: 16px; color: #1f6feb;")
        self.layout().addWidget(header)

        self._panel = CapabilityTable()
        self._panel.capability_changed.connect(self._on_capability_changed)
        self.layout().addWidget(self._panel)

        self._status = QtWidgets.QLabel("No device connected")
        self.layout().addWidget(self._status)

        self._panel.set_device(device)
        self._status.setText("Device connected - refreshing capabilities" if device is not None else "No device connected")

    def set_device(self, device: Device | None) -> None:
        self._status.setText("No device connected" if device is None else "Device connected - refreshing capabilities")
        self._panel.set_device(device)
        self._status.setStyleSheet("color: #1f6feb;" if device is not None else "color: #555;")

    def _on_capability_changed(self, name: str, enabled: bool) -> None:
        self._status.setText(f"Capability '{name}' enabled={enabled}")
