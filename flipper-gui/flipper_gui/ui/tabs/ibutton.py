"""iButton tab.

Wire protocol: newline-separated UTF-8 lines.
  * ``ibutton read``           — read an iButton key.
  * ``ibutton write <data_hex:str>`` — write a key.
  * ``ibutton add_manually <data_hex:str>`` — manually add (Dallas / Cyfral).
"""

from __future__ import annotations

from typing import Iterable, Tuple

from . import TabBase

__all__ = ["IButtonTab"]


class IButtonTab(TabBase):
    FEATURE = "ibutton"
    TITLE = "iButton"

    COMMANDS: Iterable[Tuple[str, dict]] = [
        ("read", {
            "desc": "Read an iButton key",
            "args": [],
        }),
        ("write", {
            "desc": "Write a key",
            "args": [("data_hex", "hex")],
        }),
        ("add_manually", {
            "desc": "Manually add a key (Dallas / Cyfral / Metakom)",
            "args": [("data_hex", "hex")],
        }),
    ]

    def _render(self, lines: list[str]) -> None:
        super()._render(lines)
        for ln in lines:
            if ":" in ln:
                key, _, val = ln.partition(":")
                self.log.append(f"  {key.strip()}: {val.strip()}")
