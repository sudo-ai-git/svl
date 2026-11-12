"""Shared pytest configuration for the SVL suite.

The suite must import the `svl` package from the workspace root, which is not on
`sys.path` when pytest is invoked from elsewhere.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def wasmtime_module():
    """The `wasmtime` module, or a hard failure.

    A skipped execution gate is not a passing gate: every test that compiles to WASM
    must actually assemble (and usually run) it. CI installs wasmtime, so an absent
    runtime here is an environment defect, not a reason to pass quietly.
    """
    try:
        import wasmtime
    except ImportError as exc:                         # pragma: no cover
        pytest.fail(f"wasmtime is required for SVL execution tests ({exc}); "
                    f"install it with `pip install wasmtime`")
    return wasmtime


@pytest.fixture(scope="session")
def z3_module():
    try:
        import z3
    except ImportError as exc:                         # pragma: no cover
        pytest.fail(f"z3-solver is required for the SMT tests ({exc})")
    return z3


def assemble(wasmtime_module, wat: str):
    """Parse AND validate WAT. `wat2wasm` only parses; `Module` is what validates."""
    binary = wasmtime_module.wat2wasm(wat)
    engine = wasmtime_module.Engine()
    return wasmtime_module.Module(engine, binary), engine


def instantiate(wasmtime_module, module, engine, host_out=None):
    """Instantiate a module with the host imports the SVL ABI declares."""
    store = wasmtime_module.Store(engine)
    linker = wasmtime_module.Linker(engine)
    i32 = wasmtime_module.ValType.i32()
    written = []
    linker.define_func("env", "print", wasmtime_module.FuncType([i32, i32], []),
                       lambda ptr, n: written.append((ptr, n)))
    linker.define_func("env", "print_int", wasmtime_module.FuncType([i32], []),
                       lambda v: written.append(v))
    linker.define_func("env", "putc", wasmtime_module.FuncType([i32], []),
                       lambda c: written.append(c))
    linker.define_func("env", "clear", wasmtime_module.FuncType([], []), lambda: None)
    linker.define_func("env", "malloc", wasmtime_module.FuncType([i32], [i32]), lambda n: 1024)
    linker.define_func("env", "read_key", wasmtime_module.FuncType([], [i32]), lambda: -1)
    linker.define_func("env", "iterator_next", wasmtime_module.FuncType([i32], [i32]), lambda h: 0)
    linker.define_func("env", "await", wasmtime_module.FuncType([i32], [i32]), lambda x: x)
    instance = linker.instantiate(store, module)
    return instance, store, written


def run_main(wasmtime_module, wat: str, export: str = None):
    """Compile-and-run helper: assemble, instantiate, invoke the exported main.

    The export name is `<module>_main`; when it is not given it is read from the WAT so a
    test does not have to know the module's name.
    """
    module, engine = assemble(wasmtime_module, wat)
    instance, store, _ = instantiate(wasmtime_module, module, engine)
    if export is None:
        import re
        match = re.search(r'\(export "([^"]+_main)"', wat)
        export = match.group(1) if match else "m_main"
    return instance.exports(store)[export](store)
