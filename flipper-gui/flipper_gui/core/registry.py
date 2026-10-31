"""Command lookup + discovery (plugin-style registry).

Backends (USB-serial, BLE, RF) only need to speak the wire format; the
registry is the single source of truth for what the GUI may ask the device
to do.
"""

from __future__ import annotations

from .commands import Command

__all__ = ["CommandRegistry", "register"]


class CommandRegistry:
    """Lookup table for versioned commands."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, cmd: Command) -> None:
        self._commands[cmd.name] = cmd

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def list_commands(self) -> list[str]:
        return sorted(self._commands)

    def has(self, name: str) -> bool:
        return name in self._commands

    def describe(self, name: str) -> str | None:
        cmd = self.get(name)
        return cmd.description if cmd else None


def register(registry: "CommandRegistry", cmd: "Command") -> "Command":
    """Register a command and return it."""
    registry.register(cmd)
    return cmd
