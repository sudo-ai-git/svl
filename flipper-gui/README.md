# flipper-gui

A modular desktop GUI for communicating with a [Flipper Zero](https://flipperzero.one).

The GUI is the **host-side** application: it provides a UI for monitoring and controlling the Flipper, while the Flipper's firmare remains C/CM3 on the STM32. Everything that talks to the device (USB-serial, BLE, and RF transports) is abstracted behind a single pluggable interface so new transports or feature tabs can be added independently.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
flipper-gui
```

## Recommended for the *most optimal* host-side communication layer

| Layer | Tool |
|---|---|
| USB-serial (data) | `pyserial` |
| BLE (GATT) | `bleak` |
| RF / Sub-1 GHz | `cython`/`ctypes` bound to the CC1101 (extension seam behind `comm/base.py`) |
| GUI | PySide6 (Qt) — same ecosystem as the qFlipper app |

See `docs/blueprint.md` for the full architecture, module layout, build phases, and verification gates.

## Structure

```
docs/blueprint.md      # the build blueprint (language decision, architecture, phases)
flipper_gui/core/      # domain: devices, command registry
flipper_gui/comm/      # transports: usb_serial, ble, rf, session
flipper_gui/ui/        # Qt GUI: app, main_window, tabs
flipper_gui/tests/     # pytest suite
```

## Commands

```bash
pytest -q                          # run the test suite
python -m flipper_gui comm --probe # enumerate connected Flipper-like serial devices
```
