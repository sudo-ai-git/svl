#!/usr/bin/env python3
"""Spike 013: make the REPL actually evaluate by wrapping input in a module (F12)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import run_wat, verdict                           # noqa: E402
import svl.compiler_wasm as cw                                  # noqa: E402


def repl_eval(line):
    """The proposed fix: wrap a bare line in `module repl { func main() ... }`."""
    src = f"module repl {{ func main() type int {{ {line} }} }}"
    wat = cw.compile_file_to_wasm(src)
    rv, _ = run_wat(wat, export="repl_main")
    return rv


def main():
    try:
        rv1 = repl_eval("let x = 1 return x")
        rv2 = repl_eval("let x = 1 return x + 1")
        ok = (rv1 == 1 and rv2 == 2)
        return verdict("013-repl-evaluates", ok,
                       f"`let x = 1` -> {rv1} (want 1); `let x = 1 return x + 1` -> {rv2} (want 2)")
    except Exception as exc:
        return verdict("013-repl-evaluates", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
