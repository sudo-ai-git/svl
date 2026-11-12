#!/usr/bin/env python3
"""Spike 011: link imports by resolving the file and appending its modules (F10)."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import run_wat, verdict                           # noqa: E402
import svl.compiler_wasm as cw                                  # noqa: E402


def main():
    # Two modules in ONE source: does a cross-module call resolve via module$func?
    src = ("module a { func answer() type int { return 42 } }"
           " module b { func main() type int { return answer() } }")
    try:
        wat = cw.compile_file_to_wasm(src)
        rv, _ = run_wat(wat)
        namespaced = "a$answer" in wat
        ok = (rv == 42) and namespaced
        return verdict("011-import-link-or-reject", ok,
                       f"cross-module call returned {rv} (want 42); "
                       f"namespaced callee present={namespaced}")
    except Exception as exc:
        return verdict("011-import-link-or-reject", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
