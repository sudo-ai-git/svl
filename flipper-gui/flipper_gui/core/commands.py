"""Versioned command schema.

Every command dispatched by the GUI is declared here with its name,
description, argument schema, and a handler. This is the single source of
truth for the feature set and makes protocol drift auditable.

Handler contract: ``handler(device, args, payload) -> list[str]``. The
handler receives the :class:`Device` (transport + capability set), the
declared arguments, and an optional wire payload; it returns the lines the
GUI renders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Allowed wire payloads.
PAYLOAD_TEXT = "text"
PAYLOAD_JSON = "json"
PAYLOAD_BYTES = "bytes"


@dataclass(frozen=True)
class Command:
    """A single, versioned command the device understands."""

    name: str
    description: str = ""
    args: tuple[str, ...] = ()
    payload: str = PAYLOAD_TEXT
    requires_connected: bool = True
    handler: Callable[..., list[str]] | None = None

    def execute(self, device: object, args: list[str] | None = None, payload: object | None = None) -> list[str] | None:
        if self.requires_connected:
            if device is None or not hasattr(device, "is_connected") or not device.is_connected():
                return None
        if self.handler is None:
            return None
        return self.handler(device, args or [], payload)
