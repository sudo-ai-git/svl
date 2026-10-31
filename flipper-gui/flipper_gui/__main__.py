"""Entry point. Launch the GUI with: python -m flipper_gui --gui
Query transports with:  python -m flipper_gui --probe
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .log import get_logger

logger = get_logger("flipper-gui")


def _probe() -> int:
    """List serial devices that look like a Flipper (by device file)."""
    from .comm.usb_serial import UsbSerialTransport

    found = UsbSerialTransport.probe()
    if found:
        for path in sorted(set(found)):
            print(path)
        return 0
    print("no Flipper-like serial devices found (expected when none are connected)", file=sys.stderr)
    return 1


def _run_transport(args) -> int:
    factories = {
        "usb_serial": ("flipper_gui.comm.usb_serial", "UsbSerialTransport", {"path": args.path, "baud": args.baud}),
        "ble": ("flipper_gui.comm.ble", "BleTransport", {"address": args.path or "00:00:00:00:00:00"}),
        "rf": ("flipper_gui.comm.rf", "RFTxTransport", {}),
    }
    mod_name, cls_name, kwargs = factories[args.transport]
    try:
        mod = __import__(mod_name, fromlist=[cls_name])
        T = getattr(mod, cls_name)
        t = T(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.exception("cannot build %s: %s", args.transport, e)
        return 1

    try:
        if not t.connect():
            logger.error("connect() failed")
            return 1
        if args.command:
            out = t.command(args.command.split(), args.command_arg or None)
            if out is not None:
                print("\n".join(out))
        t.disconnect()
        return 0
    except Exception as e:  # noqa: BLE001
        logger.exception("unhandled error: %s", e)
        return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="flipper-gui")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--probe", action="store_true", help="enumerate connected Flipper serial devices")
    p.add_argument("--transport", choices=["usb_serial", "ble", "rf"], default="usb_serial")
    p.add_argument("--path", default="")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--command", help="run a single command over the transport (debug)")
    p.add_argument("--command-arg", action="append", default=[], help="repeatable argument for the command")
    args = p.parse_args(argv)

    if args.probe:
        return _probe()
    return _run_transport(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
