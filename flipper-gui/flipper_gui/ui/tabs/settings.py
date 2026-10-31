"""Settings tab.

Wire protocol: newline-separated UTF-8 lines.
  * ``config get <key:str>``   — read a setting.
  * ``config set <key:str> <value:str>`` — write a setting.
  * ``config bluetooth <on|off>``
  * ``config lcd <on|off>``
  * ``config power <sleep|legacy>``
"""

from __future__ import annotations

from typing import Iterable, Tuple

from . import TabBase

__all__ = ["SettingsTab"]


class SettingsTab(TabBase):
    FEATURE = "settings"
    TITLE = "Settings"

    COMMANDS: Iterable[Tuple[str, dict]] = [
        ("get", {
            "desc": "Read a setting",
            "args": [("key", "key")],
        }),
        ("set", {
            "desc": "Write a setting",
            "args": [("key", "key"), ("value", "value")],
        }),
        ("bluetooth", {
            "desc": "Bluetooth on / off",
            "args": [("state", "on | off")],
        }),
        ("lcd", {
            "desc": "LCD backlight on / off",
            "args": [("state", "on | off")],
        }),
        ("power", {
            "desc": "Power mode: sleep or legacy",
            "args": [("mode", "sleep | legacy")],
        }),
    ]

    def _render(self, lines: list[str]) -> None:
        super()._render(lines)
        for ln in lines:
            if ":" in ln:
                key, _, val = ln.partition(":")
                self.log.append(f"  {key.strip()}: {val.strip()}")
