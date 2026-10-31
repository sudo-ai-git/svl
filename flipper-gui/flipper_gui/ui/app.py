"""Qt application bootstrap.

Importing this module requires a GUI backend. Install the optional GUI
dependency when you intend to run the window::

    pip install "flipper-gui[gui]"
"""

from __future__ import annotations

import sys

from PySide6 import QtWidgets

from .main_window import MainWindow

__all__ = ["app", "main"]


def _build_app(args: list[str]) -> QtWidgets.QApplication:
    return QtWidgets.QApplication(args)


def main(argv: list[str] | None = None) -> int:
    """Bootstrap and run the GUI; returns the Qt exit code."""
    app = _build_app(list(sys.argv))
    window = MainWindow()
    window.show()
    return app.exec()
