"""Sub-GHz read / RAW / send tab.

Wire protocol (see docs/blueprint.md): newline-separated UTF-8 lines.
  * ``read <frequency_hz:int>`` — receive a signal at a frequency.
  * ``read_raw``                — record a RAW (undecoded) signal.
  * ``send <frequency_hz:int> <payload_hex:str>`` — emulate a remote.
  * ``scan <frequency_hz:int>`` — frequency analyser (RSSI vs frequency).
"""

from __future__ import annotations

from typing import Tuple

from . import TabBase

__all__ = ["SubGhzReadTab"]


class SubGhzReadTab(TabBase):
    """Sub-1 GHz: read, RAW and emulate."""

    FEATURE = "sub-ghz"
    TITLE = "Sub-GHz"

    COMMANDS: Iterable[Tuple[str, dict]] = [
        ("read", {
            "desc": "Read a signal at this frequency",
            "args": [("frequency_hz", "Hz (e.g. 433920000)")],
        }),
        ("read_raw", {
            "desc": "Record a RAW (undecoded) signal",
            "args": [],
        }),
        ("send", {
            "desc": "Emulate / send a remote",
            "args": [("frequency_hz", "Hz"), ("payload_hex", "hex bytes")],
        }),
        ("scan", {
            "desc": "Frequency analyser at one frequency",
            "args": [("frequency_hz", "Hz")],
        }),
    ]

    def _render(self, lines: list[str]) -> None:
        super()._render(lines)
        for ln in lines:
            if ":" in ln:
                key, _, val = ln.partition(":")
                self.log.append(f"  {key.strip()}: {val.strip()}")
