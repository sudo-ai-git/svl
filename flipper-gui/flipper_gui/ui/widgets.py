"""Reusable widgets: a device list and a status badge.

These are the smallest reusable controls the window composes from, so the
UI stays modular (tabs do not touch widgets directly).
"""

from __future__ import annotations

from PySide6 import QtWidgets


class DeviceListWidget(QtWidgets.QListWidget):
    """A plain list widget used to enumerate candidate Flipper devices."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("""
            QListWidget { border: 1px solid #333; border-radius: 6px; padding: 8px; }
            QListWidget::item { padding: 6px; }
        """)

    def set_devices(self, devices: list[str]) -> None:
        self.clear()
        self.addItems(list(devices))

    def current_device(self) -> str:
        item = self.currentItem()
        return item.text() if item is not None else ""


class StatusBadge(QtWidgets.QLabel):
    """A small status badge used in the toolbar."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("Ready", parent)
        self.setStyleSheet("""
            QLabel {
                background: #2b2b2b;
                color: #eee;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 600;
            }
        """)

    def set_type(self, kind: str) -> None:
        mapping = {
            "info": "#3b82f6",
            "connected": "#22c55e",
            "warn": "#f59e0b",
            "error": "#ef4444",
            "disconnected": "#6b7280",
        }
        self.setStyleSheet(f"background: {mapping.get(kind, '#2b2b2b')};")

    def setText(self, text: str) -> None:
        super().setText(text)
