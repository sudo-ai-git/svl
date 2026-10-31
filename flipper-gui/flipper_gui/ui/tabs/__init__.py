"""Feature tabs — the UI layer for every Flipper capability.

Each tab subclasses :class:`TabBase`, declares a ``COMMANDS`` list, and gets
a command selector, an args field, a Send button, a log, and a clear button
for free. A tab never touches the wire directly — it issues commands through
``self.device.request(name, args)`` and renders the reply.

Layout: tabs/<name>.py  →  ui.main_window  →  tab  →  device.request(...)
"""

from __future__ import annotations

from typing import Iterable, Tuple

from PySide6 import QtWidgets

from ..core.devices import Capability, Device

__all__ = ["TabBase"]


class TabBase(QtWidgets.QWidget):
    """Base for all feature tabs.

    Subclasses set ``CONDINGS`` (a list of command metadata) and ``TITLE``.
    The UI (command selector + args field + Send/Clear + log) is built
    automatically; only feature-specific rendering needs to be added.
    """

    FEATURE: str = "tab"
    COMMANDS: Iterable[Tuple[str, dict]] = []
    TITLE: str = "Module"

    def __init__(self, device: "Device", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.device = device
        self.setWindowTitle(f"Flipper GUI — {self.TITLE}")
        self._build_ui()

    # -------------------------------------------------------------- #
    # UI construction
    # -------------------------------------------------------------- #
    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        top = QtWidgets.QHBoxLayout()
        self.command_selector = QtWidgets.QComboBox()
        self.command_selector.addItem("— Choose command —")
        for name, _meta in self.COMMANDS:
            self.command_selector.addItem(name)
        self.command_selector.setMinimumWidth(260)

        self.args_line = QtWidgets.QLineEdit()
        self.args_line.setPlaceholderText("optional args ...")

        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.clicked.connect(self._send)
        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear)

        top.addWidget(self.command_selector)
        top.addWidget(self.args_line)
        top.addWidget(self.send_btn)
        top.addWidget(self.clear_btn)
        outer.addLayout(top)

        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(260)
        outer.addWidget(self.log)

    # -------------------------------------------------------------- #
    # Interaction
    # -------------------------------------------------------------- #
    def _send(self) -> None:
        name = self.command_selector.currentText()
        if not name or name.startswith("—"):
            self.log.append("No command selected.")
            return
        args = self.args_line.text().strip()
        self._line(f"$ {name}" + (f" {args}" if args else ""))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        try:
            lines = self.device.request(name, args=args.split() if args else None, timeout=5.0)
            self._render(lines)
        except Exception as exc:  # noqa: BLE001
            self._line(f"error: {exc}")

    def _clear(self) -> None:
        self.log.clear()

    def log(self, text: str) -> None:
        self._line(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    # -------------------------------------------------------------- #
    # Rendering
    # -------------------------------------------------------------- #
    def _line(self, text: str) -> None:
        self.log.append(text)

    def _render(self, lines: list[str]) -> None:
        self.log.append("\n".join(lines) if lines else "(no output / not connected)")

    def set_device(self, device: "Device | None") -> None:
        """Attach (or drop) the live device, and subscribe to its event feed.

        Receiver side of the event bus: ``device.connected`` refreshes this
        tab's status, and ``data.received`` appends the device's output so the
        log never goes behind what a user just typed.
        """
        # Drop any previous subscription so a re-connect doesn't double-sub.
        try:
            self.device.set_events(None)  # type: ignore[union-attr]
        except Exception:
            pass
        self.device = device
        self._handler = None
        if device is not None:
            self._handler = self._on_event
            try:
                device.set_events(self._handler)
            except Exception:
                pass

    def _on_event(self, event: str, payload: object) -> None:
        if event == "data.received":
            lines = payload if isinstance(payload, list) else [payload]
            for ln in lines:
                self._line(ln)
        elif event == "device.connected":
            self.refresh()

    def refresh(self) -> None:
        """Called when the device is connected or settings change."""
        self.log.append(f"[{self.TITLE}] ready (connected={self.device.is_connected()})")

    def capabilities(self) -> list["Capability"]:
        return getattr(self, "_capabilities", [])

    # Utility: commands are declared here so a tab can advertise and
    # validate its feature surface.
    @classmethod
    def command_names(cls) -> list[str]:
        return [name for name, _meta in cls.COMMANDS]
