#!/usr/bin/env python3
"""Spike 008: carry PCC proofs in a binary WASM custom section (F7)."""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402
import wasmtime                                               # noqa: E402
from svl.pcc_wasm import PCCWasmGenerator, WasmCustomSection  # noqa: E402


def to_bytes_with_proofs(module):
    """wat2wasm the plain WAT, then append a binary svl-proofs custom section."""
    binary = wasmtime.wat2wasm(module.wasm_text)
    payload = {
        "source_hash": module.source_hash,
        "proofs": [{"layer": p.layer, "passed": p.passed,
                    "checksum": p.checksum, "details": p.details}
                   for p in module.proofs],
    }
    return binary + WasmCustomSection.create_proof_section(payload)


def extract_custom_sections(binary):
    """Minimal WASM section walker: return [(section_id, payload)]."""
    out = []
    i = 8                                    # skip magic + version
    while i < len(binary):
        sid = binary[i]; i += 1
        size, n = 0, 0
        while True:
            b = binary[i]; i += 1
            size |= (b & 0x7F) << n
            n += 7
            if not (b & 0x80):
                break
        out.append((sid, binary[i:i + size]))
        i += size
    return out


def main():
    src = "module m { func main() type int { return 7 } }"
    try:
        module = PCCWasmGenerator().generate(src)
        binary = to_bytes_with_proofs(module)
        engine = wasmtime.Engine()
        wasmtime.Module(engine, binary)          # VALIDATES

        found = None
        for sid, payload in extract_custom_sections(binary):
            if sid == 0:
                # payload = name_len (LEB) + name + data
                nl = payload[0]
                name = payload[1:1 + nl].decode()
                if name == "svl-proofs":
                    found = json.loads(payload[1 + nl:].decode())
        ok = found is not None and found.get("source_hash") == module.source_hash
        layers = [p["layer"] for p in found["proofs"]] if found else []
        return verdict("008-pcc-custom-section", ok,
                       f"module validated; section recovered, layers={layers}")
    except Exception as exc:
        return verdict("008-pcc-custom-section", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
