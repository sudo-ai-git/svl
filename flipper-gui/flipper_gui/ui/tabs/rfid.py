"""125 kHz RFID tab.

Wire protocol: newline-separated UTF-8 lines.
  * ``rfid read``            — read a card/tag.
  * ``rfid write <data_hex:str>`` — write to a T5577 blank.
  * ``rfid add_manually <data_hex:str>`` — manually add a tag (EM4100 etc.).
"""

from __future__ import annotations

from typing import Iterable, Tuple

from . import TabBase

__all__ = ["RfidTab"]


class RfidTab(TabBase):
    FEATURE = "rfid"
    TITLE = "RFID (125 kHz)"

    COMMANDS: Iterable[Tuple[str, dict]] = [
        ("read", {
            "desc": "Read a 125 kHz card / tag",
            "args": [],
        }),
        ("write", {
            "desc": "Write data to a T5577 blank",
            "args": [("data_hex", "hex bytes")],
        }),
        ("add_manually", {
            "desc": "Add a manual tag (EM4100 / H10301 ... )",
            "args": [("data_hex", "hex bytes")],
        }),
    ]

    def _render(self, lines: list[str]) -> None:
        super()._render(lines)
        for ln in lines:
            if ":" in ln:
                key, _, val = ln.partition(":")
                self.log.append(f"  {key.strip()}: {val.strip()}")
