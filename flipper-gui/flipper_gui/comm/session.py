"""Event bus + session: wires a Transport to a Device and publishes events.

The session owns the two "glue" threads:

  * **send loop**: calls ``Device.command()`` when a tab asks for it.
  * **receive loop**: calls ``Transport.receive()`` on an interval and
    dispatches any bytes as bus events (so UI tabs never block on I/O).

This keeps a tab's request/response model clean while the bus carries
asynchronous events (``device.connected``, ``device.disconnected``,
``rf.send``, vendor/JSON payloads, etc.).
"""

from __future__ import annotations

import logging
import threading
import time

from .base import Transport
from ..core.devices import Device, DeviceInfo
from ..core.registry import CommandRegistry

logger = logging.getLogger("flipper_gui.comm.session")


class Session:
    """Owns a Device (wrapping a Transport) and forwards its events onto the bus."""

    def __init__(self, device: Device, transport: Transport, registry: CommandRegistry | None = None,
                 interval: float = 0.1) -> None:
        self.device = device
        self.transport = transport
        self.registry = registry or device.registry
        self.interval = interval
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        # Keep the receive loop responsive but bounded.
        while self._running:
            try:
                data = self.transport.receive()
            except Exception:  # noqa: BLE001
                data = None
            if data:
                self._handle_payload(data)
            time.sleep(self.interval)

    def _handle_payload(self, data: bytes) -> None:
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            return
        lines = [ln for ln in text.splitlines() if ln.strip()]
        for ln in lines:
            self._publish("data.received", {"text": ln, "bytes": len(data)})

    def _publish(self, event: str, payload: object) -> None:
        # Device.push_event is the only bus boundary the UI subscribes to.
        dest = getattr(self.device, "events", None)
        if dest is not None:
            try:
                dest(self.device, event, payload)
            except Exception:  # noqa: BLE001
                logger.exception("event publish failed: %s", event)
