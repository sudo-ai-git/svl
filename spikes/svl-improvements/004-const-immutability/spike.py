#!/usr/bin/env python3
"""Spike 004: refuse assignment to a `const` at compile time (F6)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import run_wat, verdict                                   # noqa: E402
import svl.compiler_wasm as cw                                          # noqa: E402
from svl.compiler_wasm import WasmMutability                           # noqa: E402
from svl.parser_rd import Ident                                        # noqa: E402

_orig_assign = cw.WasmCompiler._compile_assign


def patched_assign(self, expr):
    target = expr.target
    if isinstance(target, Ident) and target.name in self.state.globals:
        if self.state.globals[target.name].mutability == WasmMutability.CONST:
            raise SyntaxError(
                f"cannot assign to const '{target.name}' at line "
                f"{getattr(target, 'line', '?')}"
            )
    return _orig_assign(self, expr)


def main():
    cw.WasmCompiler._compile_assign = patched_assign

    bad = "module m { const c: int = 5 func main() type int { c = 6 return c } }"
    good = "module m { var c: int = 5 func main() type int { c = 6 return c } }"
    try:
        refused = False
        try:
            cw.compile_file_to_wasm(bad, strict=False)
        except SyntaxError as exc:
            refused = "const" in str(exc)
        rv, _ = run_wat(cw.compile_file_to_wasm(good, strict=False))
        ok = refused and rv == 6
        return verdict("004-const-immutability", ok,
                       f"const assignment refused = {refused}; var still works (returned {rv})")
    except Exception as exc:
        return verdict("004-const-immutability", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
