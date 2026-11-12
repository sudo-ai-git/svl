#!/usr/bin/env python3
"""Spike 003: short-circuit `&&` / `||` with a value-producing `if` (F3)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import run_wat, verdict                                   # noqa: E402
import svl.compiler_wasm as cw                                          # noqa: E402

_orig_binary = cw.WasmCompiler._compile_binary_expr


def patched_binary(self, expr):
    if expr.operator in ('&&', '||'):
        func = self.state.current_function
        self._compile_expr(expr.left)
        func.body.append('if (result i32)')
        if expr.operator == '&&':
            self._compile_expr(expr.right)
            func.body.append('i32.const 0')
            func.body.append('i32.ne')
            func.body.append('else')
            func.body.append('i32.const 0')
        else:
            func.body.append('i32.const 1')
            func.body.append('else')
            self._compile_expr(expr.right)
            func.body.append('i32.const 0')
            func.body.append('i32.ne')
        func.body.append('end')
        return
    return _orig_binary(self, expr)


def main():
    cw.WasmCompiler._compile_binary_expr = patched_binary
    # x != 0 && 10/x > 1 : with x=0 the left is FALSE -> the division must be skipped.
    src = ("module m { func f(x: int) type int {"
           " let r = x != 0 && 10 / x > 1 return r }"
           " func main() type int { return f(0) } }")
    try:
        rv, _ = run_wat(cw.compile_file_to_wasm(src, strict=False))
        ok = (rv == 0)
        return verdict("003-short-circuit", ok,
                       f"f(0) returned {rv} (correct 0, no division-by-zero trap)")
    except Exception as exc:
        return verdict("003-short-circuit", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
