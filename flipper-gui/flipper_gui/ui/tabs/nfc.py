"""NFC tab.

Wire protocol: newline-separated UTF-8 lines.
  * ``nfc read``                 — read a card.
  * ``nfc save <name:str>``      — save a card.
  * ``nfc emulate <name:str>``   — emulate a saved card.
  * ``nfc mfkey32``              — recover MIFARE Classic keys (MFKey32).
  * ``nfc magic <name:str>``     — write a magic card.
"""

from __future__ import annotations

from typing import Iterable, Tuple

from . import TabBase

__all__ = ["NfcTab"]


class NfcTab(TabBase):
    FEATURE = "nfc"
    TITLE = "NFC (13.56 MHz)"

    COMMANDS: Iterable[Tuple[str, dict]] = [
        ("read", {
            "desc": "Read a card",
            "args": [],
        }),
        ("save", {
            "desc": "Save a card",
            "args": [("name", "name")],
        }),
        ("emulate", {
            "desc": "Emulate a saved card",
            "args": [("name", "name")],
        }),
        ("mfkey32", {
            "desc": "Recover MIFARE Classic keys (Crypto-1)",
            "args": [],
        }),
        ("magic", {
            "desc": "Write a magic card",
            "args": [("name", "name")],
        }),
    ]

    def _render(self, lines: list[str]) -> None:
        super()._render(lines)
        for ln in lines:
            if ":" in ln:
                key, _, val = ln.partition(":")
                self.log.append(f"  {key.strip()}: {val.strip()}")
