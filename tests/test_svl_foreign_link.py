"""Foreign-module linking: `extern "c"` satisfied by a compiled WASM module.

Before this, an `extern "c"` import could only be satisfied by a host Python callback,
so there was no way to hand a program a compiled C/Rust module.  These tests pin the
link path and, more importantly, the LINK-TIME signature gate: a missing or
mismatched foreign export must be refused before the program runs, not trap later.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

wasmtime = pytest.importorskip("wasmtime")

from svl.compiler_wasm import compile_file_to_wasm
from svl.foreign_link import (
    HOST_IMPORTS,
    ForeignModuleError,
    foreign_exports,
    load_foreign_module,
    plan_links,
)
from svl.repl import run_wat


def _wasm(wat: str) -> bytes:
    return wasmtime.wat2wasm(wat)


def _program(body: str, extern: str = "") -> str:
    return f"module m {{\n  {extern}\n  func main() type int {{\n    {body}\n  }}\n}}\n"


ADD_WAT = ('(module (func (export "svl_add") (param i32 i32) (result i32) '
           'local.get 0 local.get 1 i32.add))')
WRONG_WAT = '(module (func (export "svl_add") (param i32) (result i32) local.get 0))'
LEN_WAT = ('(module (func (export "svl_len") (param i32) (result i32) local.get 0))')


class TestLinkedExecution:
    def test_extern_call_reaches_the_foreign_module(self):
        """The actual interop path: SVL calls a compiled foreign function."""
        wat = compile_file_to_wasm(
            _program("return svl_add(40, 2)",
                     'extern "c" func svl_add(a: int, b: int) type int'))
        rv, _out = run_wat(wat, foreign=[_wasm(ADD_WAT)])
        assert rv == 42

    def test_two_foreign_modules(self):
        wat = compile_file_to_wasm(
            _program("return svl_add(svl_len(7), 1)",
                     'extern "c" func svl_add(a: int, b: int) type int\n'
                     '  extern "c" func svl_len(p: int) type int'))
        rv, _out = run_wat(wat, foreign=[_wasm(LEN_WAT), _wasm(ADD_WAT)])
        assert rv == 8

    def test_foreign_module_with_its_own_memory(self):
        """A foreign module exporting a memory links without disturbing the SVL side."""
        wat_c = ('(module (memory (export "mem") 1) '
                 '(func (export "svl_add") (param i32 i32) (result i32) '
                 'local.get 0 local.get 1 i32.add))')
        svl = compile_file_to_wasm(
            _program("return svl_add(20, 22)",
                     'extern "c" func svl_add(a: int, b: int) type int'))
        rv, _out = run_wat(svl, foreign=[_wasm(wat_c)])
        assert rv == 42

    def test_host_stubs_still_work_without_foreign_modules(self):
        """No `extern` in the program: behaviour is unchanged."""
        wat = compile_file_to_wasm(
            'module m { func main() type void { print("hi") } }')
        _rv, out = run_wat(wat)
        assert out == b"hi"


class TestLinkTimeGate:
    def test_missing_foreign_export_is_refused_by_name(self):
        wat = compile_file_to_wasm(
            _program("return svl_add(40, 2)",
                     'extern "c" func svl_add(a: int, b: int) type int'))
        with pytest.raises(ForeignModuleError) as ei:
            run_wat(wat)
        assert "svl_add" in str(ei.value)
        assert "no linked module exports it" in str(ei.value)

    def test_signature_mismatch_is_refused_with_both_signatures(self):
        wat = compile_file_to_wasm(
            _program("return svl_add(40, 2)",
                     'extern "c" func svl_add(a: int, b: int) type int'))
        with pytest.raises(ForeignModuleError) as ei:
            run_wat(wat, foreign=[_wasm(WRONG_WAT)])
        msg = str(ei.value)
        assert "svl_add" in msg and "signature mismatch" in msg
        assert "'i32', 'i32'" in msg and "'i32'" in msg

    def test_non_wasm_input_is_refused(self):
        wat = compile_file_to_wasm(
            _program("return svl_add(1, 2)",
                     'extern "c" func svl_add(a: int, b: int) type int'))
        with pytest.raises(ForeignModuleError) as ei:
            run_wat(wat, foreign=[b"(module (func))"])   # WAT text, not a binary
        assert "not a WASM module" in str(ei.value)

    def test_invalid_wasm_is_refused(self):
        engine = wasmtime.Engine()
        with pytest.raises(ForeignModuleError) as ei:
            load_foreign_module(engine, b"\x00asm" + b"\xde\xad\xbe\xef" * 4)
        assert "failed to validate" in str(ei.value)


class TestPlanLinks:
    def test_host_imports_are_not_required_from_foreign_modules(self):
        """`print` et al. are builtin; they must never be demanded from a link."""
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, compile_file_to_wasm(
            'module m { func main() type void { print("x") } }'))
        _mods, unresolved = plan_links(module, [])
        assert unresolved == []

    def test_every_builtin_name_is_recognised(self):
        """If a host stub is renamed here but not in foreign_link, the link would
        demand it from a foreign module.  Pin the set."""
        assert HOST_IMPORTS == {
            "print", "print_int", "putc", "clear", "malloc", "iterator_next", "await",
        }

    def test_foreign_exports_indexes_functions_only(self):
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, _wasm(
            '(module (memory (export "mem") 1) '
            '(func (export "f") (param i32) (result i32) local.get 0))'))
        assert list(foreign_exports(module)) == ["f"]
