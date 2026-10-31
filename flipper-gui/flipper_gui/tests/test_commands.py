"""Tests for the versioned command model."""

from __future__ import annotations

import pytest

from flipper_gui.core.commands import Command, PAYLOAD_TEXT, PAYLOAD_JSON, PAYLOAD_BYTES


class TestCommand:
    def test_default_payload_is_text(self) -> None:
        cmd = Command(name="echo")
        assert cmd.payload == PAYLOAD_TEXT

    def test_payload_variants(self) -> None:
        assert PAYLOAD_JSON == "json"
        assert PAYLOAD_BYTES == "bytes"

    def test_requires_connected_default(self) -> None:
        cmd = Command(name="x")
        assert cmd.requires_connected is True


class TestCommandExecute:
    def test_execute_returns_none_without_bus(self) -> None:
        cmd = Command(name="x", handler=lambda d, a, p: ["hi"])
        out = cmd.execute(None, ["a"], None)
        assert out is None

    def test_execute_with_connected_device(self) -> None:
        class D:
            def is_connected(self) -> bool:
                return True

            def disconnect(self) -> None:
                pass

            def send(self, data: bytes) -> bool:
                return True

            def receive(self) -> bytes | None:
                return None

        cmd = Command(name="x", handler=lambda d, a, p: ["hi"])
        out = cmd.execute(D(), ["a"], None)
        assert out == ["hi"]
