"""Application settings with JSON persistence and defaults."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Canonical default location per platform (user-writable), with a local override.
DEFAULT_DIR = Path(os.environ.get("FLIPPER_GUI_CONFIG_DIR", Path.home() / ".config" / "flipper-gui"))


@dataclass
class Settings:
    transport_type: str = "usb_serial"          # usb_serial | ble | rf
    transport_path: str = ""                     # /dev/ttyACM0 | COM3 | BLE address
    transport_baud: int = 115200
    ble_address: str = ""
    log_level: str = "INFO"
    recent_devices: list[str] = field(default_factory=list)
    gui_tab: str = "device_info"

    def to_path(self) -> Path:
        return DEFAULT_DIR / "settings.json"

    @staticmethod
    def _defaults() -> "Settings":
        return Settings()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        p = Path(path) if path else cls._defaults().to_path()
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            return cls(**raw)
        return cls()

    def save(self) -> None:
        self.to_path().parent.mkdir(parents=True, exist_ok=True)
        self.to_path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @property
    def bus(self) -> str:
        """Normalized transport selection used by the UI to pick a backend."""
        if self.transport_type == "usb_serial":
            return "usb_serial"
        if self.transport_type == "ble":
            return "ble"
        return "rf"
