#!/usr/bin/env python3
"""Spike 005: lower `print(...)` by the argument's inferred type (F5)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import run_wat, verdict                                   # noqa: E402
import svl.compiler_wasm as cw                                          # noqa: E402
from svl.parser_rd import Literal, Ident                           # noqa: E402

_orig_call = cw.WasmCompiler._compile_call_expr


def _type_name(self, expr):
    if isinstance(expr, Ident):
        t = self._inferred_local_type(self.state.current_function.name, expr.name)
    else:
        t = self._inferred_expr_type(expr)
    if t is None:
        return None
    if getattr(t, 'kind', None) == 'prim':
        return str(t)
    return getattr(t, 'kind', None)


def patched_call(self, expr):
    if expr.callee == 'print' and len(expr.arguments) == 1:
        arg = expr.arguments[0]
        if not (isinstance(arg, Literal) and arg.literal_type == 'string'):
            func = self.state.current_function
            callee = self._resolve_callee(expr.callee, getattr(expr, 'line', '?'))
            tname = _type_name(self, arg)
            if tname in ('int', 'bool'):
                self._compile_expr(arg)
                func.body.append(f'call {self._resolve_callee("print_int", getattr(expr, "line", "?"))}')
                return
            if tname == 'string':
                tmp = self._temp_local(func, 's')
                self._compile_expr(arg)
                func.body.append(f'local.set ${tmp}')
                func.body.append(f'local.get ${tmp}')
                func.body.append('i32.const 4')
                func.body.append('i32.add')
                func.body.append(f'local.get ${tmp}')
                func.body.append('i32.load')
                func.body.append(f'call {callee}')
                return
            raise SyntaxError(
                f"print() does not support {tname or 'this'} argument "
                f"(line {getattr(expr, 'line', '?')})"
            )
    return _orig_call(self, expr)


def main():
    cw.WasmCompiler._compile_call_expr = patched_call
    src = ("module m { func main() type void { let x = 5 print(x)"
           " let s = \"hi\" print(s) return } }")
    try:
        wat = cw.compile_file_to_wasm(src, strict=False)
        rv, out = run_wat(wat)
        ok = (out.decode("utf-8", "replace") == "5hi")
        return verdict("005-print-type-dispatch", ok,
                       f"printed {out!r} (expected '5hi'); module validated")
    except Exception as exc:
        return verdict("005-print-type-dispatch", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
