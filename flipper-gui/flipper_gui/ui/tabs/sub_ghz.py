"""Sub-GHz analysis & vendor-support tab.

Wire protocol (see docs/blueprint.md): newline-separated UTF-8 lines.
  * ``scan <frequency_hz:int>``     — Frequency Analyzer (RSSI vs frequency).
  * ``scan <start> <end> <step>``   — sweep a band.
  * ``vendor <vendor_id:str>``      — vendor decode table.
  * ``config manual <on|off>``      — manual / hopping frequency mode.
  * ``config modulation <mode>``    — manual modulation (AM270/AM650/FM238/...).
"""

from __future__ import annotations

from typing import Iterable, Tuple

from . import TabBase

__all__ = ["SubGhzAnalysisTab"]


class SubGhzAnalysisTab(TabBase):
    FEATURE = "sub-ghz"
    TITLE = "Sub-GHz / Analysis"

    COMMANDS: Iterable[Tuple[str, dict]] = [
        ("scan", {
            "desc": "Frequency Analyzer at one frequency",
            "args": [("frequency_hz", "Hz")],
        }),
        ("sweep", {
            "desc": "Sweep a band <start> <end> <step_hz>",
            "args": [("start", "Hz"), ("end", "Hz"), ("step", "Hz")],
        }),
        ("vendor", {
            "desc": "Vendor decode table for a vendor id",
            "args": [("vendor_id", "hex vendor id")],
        }),
        ("config_manual", {
            "desc": "Set manual / hopping frequency mode",
            "args": [("mode", "on | off")],
        }),
        ("config_modulation", {
            "desc": "Manual modulation mode",
            "args": [("mode", "AM270 / AM650 / FM238 / FM476")],
        }),
    ]

    def _render(self, lines: list[str]) -> None:
        super()._render(lines)
        for ln in lines:
            if ":" in ln:
                key, _, val = ln.partition(":")
                self.log.append(f"  {key.strip()}: {val.strip()}")
