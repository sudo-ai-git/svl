"""Universal remote (IR) tab.

Wire protocol: newline-separated UTF-8 lines.
  * ``ir learn``          — learn a new remote.
  * ``ir send <hex:str>`` — send an IR payload (38 kHz carrier).
  * ``ir universal <dev:str>`` — send a universal (dictionary) command.
"""

from __future__ import annotations

from typing import Iterable, Tuple

from . import TabBase

__all__ = ["InfraredTab"]


class InfraredTab(TabBase):
    FEATURE = "infrared"
    TITLE = "Infrared"

    COMMANDS: Iterable[Tuple[str, dict]] = [
        ("learn", {
            "desc": "Learn a new remote",
            "args": [],
        }),
        ("send", {
            "desc": "Send an IR payload (38 kHz carrier)",
            "args": [("hex", "hex bytes")],
        }),
        ("universal", {
            "desc": "Send a universal (dictionary) command",
            "args": [("device", "device")],
        }),
    ]

    def _render(self, lines: list[str]) -> None:
        super()._render(lines)
        for ln in lines:
            if ":" in ln:
                key, _, val = ln.partition(":")
                self.log.append(f"  {key.strip()}: {val.strip()}")
