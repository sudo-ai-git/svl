"""Reusable widgets: a device list and a status badge.

These are the smallest reusable controls the window composes from, so the
UI stays modular (tabs do not touch widgets directly).
"""

from __future__ import annotations

from typing import List

from PySide6 import QtWidgets

from ..comm.device_manager import DeviceCandidate

__all__ = ["DeviceListWidget", "StatusBadge"]


class DeviceListWidget(QtWidgets.QListWidget):
    """A list widget showing discovered Flipper candidates.

    Each item's first line is the device name, the second line is its kind
    plus path.  Constants are kept in ``self._candidates`` so the main window
    can map the row back to a real :class:`DeviceCandidate`.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._candidates: List[DeviceCandidate] = []
        self.setStyleSheet("""

        QListWidget { border: 1px solid #333; border-radius: 6px; padding: 8px; }
        QListWidget::item { padding: 6px; }

        """)

    def set_devices(self, devices: List[DeviceCandidate]) -> None:
        self.clear()
        self._candidates = list(devices)
        for c in devices:
            text = f"{c.name}\n[{c.kind}] {c.path or ''}{(' — ' + c.note) if c.note else ''}"
            self.addItem(text)

    def current_candidate(self) -> "DeviceCandidate | None":
        i = self.currentRow()
        if 0 <= i < len(self._candidates):
            return self._candidates[i]
        return None


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
