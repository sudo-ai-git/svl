#!/usr/bin/env python3
"""Spike 020: write real WASM binaries in the package manager (L3)."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402
import wasmtime                                               # noqa: E402
from svl.compiler_wasm import compile_file_to_wasm             # noqa: E402

WAT = 'module m { func main() type int { return 7 } }'


def main():
    try:
        wat = compile_file_to_wasm(WAT)
        is_text = not wat.startswith("\x00asm")
        binary = wasmtime.wat2wasm(wat)
        magic = binary[:4] == b"\x00asm"
        # the registry's own check:
        registry_check = binary[:4] == b"\x00asm"
        ok = is_text and magic and registry_check
        return verdict("020-package-manager-wat-mislabel", ok,
                       f"compile_file_to_wasm returns text={is_text}; "
                       f"wat2wasm -> magic bytes OK={magic}; registry check would pass={registry_check}")
    except Exception as exc:
        return verdict("020-package-manager-wat-mislabel", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
