"""Firmware tab.

Wire protocol: newline-separated UTF-8 lines.
  * ``fw update <channel|url:str>``  — update firmware (DEV / RC / RELEASE).
  * ``fw channel <dev|rc|release>``  — set the update channel.
  * ``fw recover``                   — enter DFU / recovery mode.
"""

from __future__ import annotations

from typing import Iterable, Tuple

from . import TabBase

__all__ = ["FirmwareTab"]


class FirmwareTab(TabBase):
    FEATURE = "firmware"
    TITLE = "Firmware"

    COMMANDS: Iterable[Tuple[str, dict]] = [
        ("update", {
            "desc": "Update firmware (channel or URL)",
            "args": [("target", "DEV / RC / RELEASE or URL")],
        }),
        ("channel", {
            "desc": "Set the update channel",
            "args": [("channel", "DEV / RC / RELEASE")],
        }),
        ("recover", {
            "desc": "Enter DFU / recovery mode",
            "args": [],
        }),
    ]

    def _render(self, lines: list[str]) -> None:
        super()._render(lines)
        for ln in lines:
            if ":" in ln:
                key, _, val = ln.partition(":")
                self.log.append(f"  {key.strip()}: {val.strip()}")
