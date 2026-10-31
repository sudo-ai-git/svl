# flipper-gui — Comprehensive Build Blueprint

Build a desktop GUI that talks to a Flipper Zero, designed to be **modular, observable, and incrementally improveable**. This blueprint is the single source of truth to work from.

---

## 1. Objective & Scope (interpretation, stated explicitly)

- **Goal:** A GUI application (host machine) that communicates with a Flipper Zero and lets a human control and observe it.
- **Scope (which Flipper capabilities the GUI exposes):** device info, firmware update, Sub-1 GHz signals (read/RAW/send), NFC (read/emulate/MFKey32/magic), 125 kHz RFID, iButton, IR remote, GPIO & modules, settings.
- **Scope (intentionally out):** on-device (Flipper-screen) apps, firmware *writing* to the MCU itself, or a GUI inside the Flipper's firmware (those use a different toolchain — C/CM3 for the firmware, mJS for the Flipper's own apps).

> Rationale for the primary language below rests on this scope split: the **device side** is C/CM3 firmware; the **host GUI + communication layer** is a separate concern that we author in Python.

---

## 2. Language Decision — "Most optimal language for communicating with the Flipper Zero"

**Recommendation: Python 3 (host GUI + communication layer).** With the Flipper firmware side left in C/CM3 (its native language; not a host GUI constraint), Python is the most optimal host language because:

1. **Three transports, one mature ecosystem:** USB-serial (`pyserial`), BLE (`bleak`), and RF (`cython`/`ctypes` bound to the CC1101 or a small extension module) are all best-in-class in Python. No C/C++ toolchain needed on the dev machine.
2. **Modularity + constant improvement:** a single-language, well-structured codebase is dramatically easier to extend with new tabs, transports, or protocol versions than a C++/Qt GUI would be for a single contributor.
3. **Ecosystem fit:** `flipperzero` (PyPI), `bleak` (BLE GATT), `pyserial`, Qt via PySide6 (the same toolkit qFlipper uses), `pytest`, `build`/`pip`. The whole stack is one language.
4. **Trade-off acknowledged:** it is *not* the most performant or the most "native" for the host. But for a GUI driven by asynchronous device events and rapid feature iteration, developer velocity and dev-observability outweigh raw throughput. If a perf-critical RF backend is ever needed, that backend is a small `cython`/`cffi` extension sealed behind the `Transport` ABC (see Shipping-C/Snippet: RF backend).

**Not recommended as primary:** pure C/C++ desktop GUI (slow iteration, unnecessary toolchain) for this scope.

---

## 3. Architecture (layered, event-driven, decoupled)

Key design choice: **no UI blocks I/O; communication and UI live in separate threads with a thread-safe event bus.** This is what makes the app testable and the feature tabs independent.

```
core/          domain (devices, command registry) — no I/O, no Qt
comm/          transports (USB-serial, BLE, RF) — no UI
ui/            Qt GUI (main window, tabs, widgets)
config/        settings persistence
log/           structured logging
tests/         pytest suite (core + comm mock; UI sanity)
```

- **Transport ABC** (`comm.base.Transport`): `connect()`, `disconnect()`, `send(bytes)`, `receive() -> bytes|None`, `on_event(callback)`. Backends implement only this interface.
- **Device model** (`core.devices.FlipperZero`): owns a `Transport`, exposes a `command registry`, publishes events. No Qt.
- **Command registry** (`core.registry`): typed command → handler map; each command is versioned + documented (so protocol changes are auditable).
- **Session** (`comm.session.Session`): wires a `Transport` to the `Device`; owns the event bus (thread-safe `queue.Queue`-backed); runs the receive loop in its own thread.
- **UI**: subscribes to events on the bus; each tab is a `QWidget` with zero knowledge of transports.

Why this is "modular": a new transport, a new Flipper variant, or a new tab is a **separate class/module** that plugs into an interface. Adding a feature = implementing one new module, not editing a monolith.

---

## 4. Module Layout (highly modular, tree per feature)

```
flipper-gui/
├── pyproject.toml                 # packaging, deps, entry point
├── README.md
├── docs/
│   └── blueprint.md               # ← this file
├── scripts/                       # local dev helpers (NOT shipped)
├── flipper_gui/
│   ├── __init__.py                # version, __all__
│   ├── __main__.py                # entry: python -m flipper_gui
│   ├── config.py                  # Settings (JSON), load/save, defaults
│   ├── log.py                     # structured logger (JSON/traceback)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── devices.py             # Device model + capability registry
│   │   ├── commands.py            # command schema + versioned commands
│   │   └── registry.py            # command registry + plugin discovery
│   ├── comm/
│   │   ├── __init__.py
│   │   ├── base.py                # Transport ABC + event emitter
│   │   ├── usb_serial.py          # pyserial USB-serial transport
│   │   ├── ble.py                 # bleak BLE GATT transport
│   │   ├── rf.py                  # Sub-1 GHz radio (CC1101) transport seam
│   │   └── session.py             # Session: wires Transport→Device→event bus
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── app.py                 # QApplication bootstrap + window icon
│   │   ├── main_window.py         # menubar, status bar, tab controller
│   │   ├── widgets.py             # reusable widgets (device list, console, badge)
│   │   └── tabs/
│   │       ├── __init__.py
│   │       ├── device_info.py     # Device Info tab
│   │       ├── signals.py         # Sub-1 GHz read/RAW/send
│   │       ├── sub_ghz.py
│   │       ├── nfc.py
│   │       ├── rfid.py
│   │       ├── ibutton.py
│   │       ├── infrared.py
│   │       ├── firmware.py        # firmware update tab
│   │       └── settings.py        # settings tab
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_devices.py
│   │   ├── test_commands.py
│   │   └── test_session.py        # comm mocked
│   └── resources/                 # icons, QML, etc.
```

Layout rule: **each of the five subsystems (`core`, `comm`, `ui`, `config`, `log`) is one importable package with an `__init__.py`; feature tabs are one package (`ui.tabs`) with one module per tab.** This makes `tree`/`ls` read as a map, so "constant improvements" = adding files, not threading logic through existing files.

---

## 5. Build Phases (each with a runnable gate; do not skip a gate)

**Phase 0 — Environment.** Python 3.11+ (`python --version`), create venv, install. *Gate:* `python -c "import PySide6, pyserial, bleak, pytest"`. If any import fails, install before proceeding.

Phase 1 — Communication abstraction + USB-serial. Implement `Transport ABC`, `usb_serial` transport, and a `USBProbe` helper that lists `/dev/ttyACM*` (macOS `/dev/cu.usbmodem*`, Windows `COM*`). *Gate:* `python -m flipper-gui --probe` lists connected Flipper-like serial devices (a clean empty list is "no devices, not an error").

**Phase 2 — Device model + command registry.** `core.devices.FlipperZero`, `core.commands` (versioned command definitions), `core.registry` (lookup). *Gate:* `pytest -q flipper_gui/tests/test_devices.py flipper_gui/tests/test_commands.py` → 0 failures.

**Phase 3 — GUI skeleton.** `ui.app` bootstrap, `ui.main_window`, status bar, device-list widget, one minimal tab (Device Info). *Gate:* `python -m flipper_gui` launches and exits 0 without crashing.

**Phase 4 — Wired tabs.** Hook the feature tabs to the `Session` (via `ui` subscribing to the event bus). *Gate:* open the "Signals"/"NFC" tab and it shows zero events → communicates (not broken). Same for "Device Info" tab showing a connected device's model.

**Phase 5 — BLE + RF transports.** Implement `ble.py` (bleak) and `rf.py` (the CC1101 seam). *Gate:* `test_session.py` uses a mock transport and exercises the full `connect→command→ack` path.

**Phase 6 — Settings + logging.** Persist last-connected serial/device in `config.py`; structured log to `./flipper_gui.log`. *Gate:* delete `~/.config/flipper-gui/settings.json`, relaunch, verify settings restored (or default).

**Phase 7 — Tests, packaging, docs.** `pytest` (all), `pip install -e .` (or `python -m build`), `README.md` with quickstart + troubleshooting. *Gate:* full `pytest` suite green; `pip install -e .` works; README quickstart reproduces Phase 0–1 on a real Flipper (optional, record as "pass" or "blocked on hardware").

---

## 6. Feature Tabs (each tab = one module; feature set comes from the `flipper-zero-docs` skill)

| Tab (`ui/tabs/X.py`) | Capability | Backend command(s) |
|---|---|---|
| `device_info.py` | Firmware channels, model, region, battery | `DeviceInfo`, `FirmwareChannel`, `DeviceInfoRegion` |
| `signals.py` | Read/RAW/send (Sub-1 GHz) | `Read`, `ReadRaw`, `Send` |
| `sub_ghz.py` | Frequency analyzer, vendor decode | `FrequencyAnalyzer`, `Decode` |
| `nfc.py` | Read, emulate, MFKey32, magic cards | `NfcRead`, `NfcEmulate`, `NfcMfkey32`, `NfcMagic` |
| `rfid.py` | 125 kHz RFID read/write | `RfidRead`, `RfidWrite` |
| `ibutton.py` | Read, write, add manually | `IButtonRead`, `IButtonWrite` |
| `infrared.py` | Learn/send IR, universal remotes | `IrLearn`, `IrSend`, `IrUniversal` |
| `firmware.py` | Firmware update (DFU) | `FirmwareUpdate` |
| `settings.py` | Settings UI mirror | `Settings*`. |

Each tab's contract: receives the connected `Device` (or a "disconnected" state), renders events, and exposes simple `QPushButton`/input widgets that call the `CommandRegistry`. A tab only touches the **core domain model**, never the transport directly.

---

## 7. Verification Plan (double-checked)

Per-phase gates above are the primary verification. The final e2e gate is run on a **real Flipper**:

```
1. Connect Flipper via USB → pyserial enumerates it (/dev/ttyACM0 / COMx).
2. python -m flipper-gui --probe        → lists it
3. Launch GUI → Device Info tab shows model/firmware/region from the connected device.
4. Send a test command (e.g., read device info) → command ack arrives on the event bus.
5. Read a RAW signal → signal payload round-trips through the bus to the Signals tab.
```

Recording the result is mandatory: `Pass` (clean return code + expected output) vs `expected X, got Y`. A number with the wrong provenance is worse than no number — record tool output as tool output, and only claim the round-trip as a round-trip once each leg is shown.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| BLE pairing on Linux requires udev rules / permissions | Document the udev rule for `hci0`/`bluetooth`; on headless or locked-down hosts, fall back to USB-serial and mark BLE "needs permission" |
| RF bit-banging unreliable on a laptop GPIO | Seal the CC1101 in `comm.rf` behind a C/C++ extension seam; prototype with the ST-Link V3 devboard's UART-first path |
| GUI freezes because `receive()` blocks the UI thread | Enforce the event bus + separate receive thread; test via `test_session.py` with a `queue.Queue` mock |
| Protocol drift in the Flipper firmware | Version every command in the registry; add a `DeviceInfo.firmware` capability check before command dispatch |
| Permissions / sandbox on macOS (App Translocation) | Sign/entitle with a dev cert, or launch with `open -a ... --args --no-sandbox` during dev |

---

## 9. Decision Record (language + architecture, one line each)

- **Primary language:** Python 3 — optimal for a modular GUI + multi-transport comm layer that must be constantly improved.
- **On-device firmware language:** C/CM3 (Flipper native) — out of this GUI's scope.
- **GUI toolkit:** PySide6 (Qt) — same ecosystem as qFlipper, fast iteration.
- **Comm model:** layered, event-bus-driven, transport-ABC pluggable.
- **Feature extent:** mirrors the `flipper-zero-docs` skill's capability list, one tab per capability.
