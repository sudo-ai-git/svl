#!/usr/bin/env python3
"""Spike 002: lower `for x in <array>` to a bounds-safe index scan (F2)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import run_wat, verdict                                   # noqa: E402
import svl.compiler_wasm as cw                                          # noqa: E402
from svl.compiler_wasm import WasmValType                              # noqa: E402
from svl.parser_rd import ArrayLit, CallExpr, Ident, LetStmt           # noqa: E402

_orig_for = cw.WasmCompiler._compile_for_stmt
_orig_let = cw.WasmCompiler._compile_let_stmt
_orig_init = cw.WasmCompiler.__init__


def _is_array_expr(e):
    if isinstance(e, ArrayLit):
        return True
    return isinstance(e, CallExpr) and e.callee == 'zeros'


def _is_array_iterable(self, expr):
    if _is_array_expr(expr):
        return True
    if isinstance(expr, Ident):
        return expr.name in getattr(self, '_array_locals', set())
    t = self._inferred_expr_type(expr)
    return bool(t is not None and getattr(t, 'kind', None) in ('array', 'tuple'))


def _compile_array_for_stmt(self, stmt):
    func = self.state.current_function
    base = f"arrbase_{self.state.label_counter}"; self.state.label_counter += 1
    idx = f"arridx_{self.state.label_counter}"; self.state.label_counter += 1
    label_start = f"$for_{self.state.label_counter}"
    label_end = f"$for_end_{self.state.label_counter}"
    self.state.label_counter += 1

    self._compile_expr(stmt.iter_expr)
    func.locals.append((base, WasmValType.I32))
    func.body.append(f'local.set ${base}')
    func.body.append('i32.const 0')
    func.locals.append((idx, WasmValType.I32))
    func.body.append(f'local.set ${idx}')

    func.body.append(f'loop {label_start}')
    func.body.append(f'block {label_end}')
    func.body.append(f'local.get ${idx}')
    func.body.append(f'local.get ${base}')
    func.body.append('i32.load')
    func.body.append('i32.ge_s')
    func.body.append(f'br_if {label_end}')

    func.locals.append((stmt.var, WasmValType.I32))
    func.body.append(f'local.get ${base}')
    func.body.append('i32.const 4')
    func.body.append('i32.add')
    func.body.append(f'local.get ${idx}')
    func.body.append('i32.const 4')
    func.body.append('i32.mul')
    func.body.append('i32.add')
    func.body.append('i32.load')
    func.body.append(f'local.set ${stmt.var}')

    self._compile_block(stmt.body)

    func.body.append(f'local.get ${idx}')
    func.body.append('i32.const 1')
    func.body.append('i32.add')
    func.body.append(f'local.set ${idx}')
    func.body.append(f'br {label_start}')
    func.body.append('end')
    func.body.append('end')


def patched_let(self, stmt):
    _orig_let(self, stmt)
    if _is_array_expr(stmt.value):
        self._array_locals.add(stmt.name)


def patched_for(self, stmt):
    if not self._is_range_loop(stmt) and _is_array_iterable(self, stmt.iter_expr):
        _compile_array_for_stmt(self, stmt)
        return
    return _orig_for(self, stmt)


def patched_init(self, *a, **k):
    _orig_init(self, *a, **k)
    self._array_locals = set()


def main():
    cw.WasmCompiler.__init__ = patched_init
    cw.WasmCompiler._compile_for_stmt = patched_for
    cw.WasmCompiler._compile_let_stmt = patched_let
    src = ("module m { func main() type int { let a = [1, 2, 3] let s = 0"
           " for x in a { s += x } return s } }")
    try:
        wat = cw.compile_file_to_wasm(src)
        rv, _ = run_wat(wat)
        no_iter = "iterator_next" not in wat
        ok = (rv == 6) and no_iter
        return verdict("002-for-in-array", ok,
                       f"returned {rv} (correct 6); iterator_next absent = {no_iter}")
    except Exception as exc:
        return verdict("002-for-in-array", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
