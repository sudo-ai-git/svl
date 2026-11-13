"""Differential execution: the reference interpreter vs the compiled WASM.

Runs one program through BOTH the tree-walking reference interpreter
(`svl.reference_interp`) and the real backend (wasmtime), captures the printed output
and the return value from each, and reports whether they agree.

This is the conformance gate the backend previously lacked: the compiler was the spec,
so a wrong answer could not be classified as a bug or as intended behaviour.
"""
import re
from typing import Any, Dict, List, Tuple


def run_wasm(source: str) -> Tuple[Any, str]:
    """Compile and run a program, returning (export value, printed output)."""
    import wasmtime
    from svl.compiler_wasm import compile_file_to_wasm

    wat = compile_file_to_wasm(source)
    binary = wasmtime.wat2wasm(wat)
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, binary)
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    i32 = wasmtime.ValType.i32()
    out: List[str] = []
    memory: List[Any] = [None]

    def _print(ptr: int, n: int) -> None:
        if memory[0] is None or n <= 0:
            return
        out.append(memory[0].read(store, ptr, ptr + n).decode('utf-8', 'replace'))

    linker.define_func('env', 'print', wasmtime.FuncType([i32, i32], []), _print)
    linker.define_func('env', 'print_int', wasmtime.FuncType([i32], []),
                       lambda v: out.append(str(v)))
    linker.define_func('env', 'putc', wasmtime.FuncType([i32], []),
                       lambda c: out.append(chr(c)))
    linker.define_func('env', 'clear', wasmtime.FuncType([], []), lambda: None)
    linker.define_func('env', 'malloc', wasmtime.FuncType([i32], [i32]), lambda n: 1024)
    linker.define_func('env', 'read_key', wasmtime.FuncType([], [i32]), lambda: -1)
    linker.define_func('env', 'iterator_next', wasmtime.FuncType([i32], [i32]), lambda h: 0)
    linker.define_func('env', 'await', wasmtime.FuncType([i32], [i32]), lambda x: x)

    instance = linker.instantiate(store, module)
    exports = instance.exports(store)
    try:
        memory[0] = exports['memory']
    except Exception:                                             # noqa: BLE001
        memory[0] = None
    match = re.search(r'\(export "([^"]+_main)"', wat)
    export = match.group(1) if match else 'm_main'
    result = exports[export](store)
    return result, ''.join(out)


def differential(source: str) -> Dict[str, Any]:
    """Run one program through both implementations and compare."""
    from svl.reference_interp import interpret

    interp_result, interp_out = interpret(source)
    wasm_result, wasm_out = run_wasm(source)
    return {
        'interpreter': {'result': interp_result, 'output': interp_out},
        'wasm': {'result': wasm_result, 'output': wasm_out},
        'agree': interp_result == wasm_result and interp_out == wasm_out,
    }


def run_suite(programs: Dict[str, str]) -> Tuple[int, int, List[str]]:
    """Run a named suite; return (agreed, total, failures)."""
    agreed = 0
    failures: List[str] = []
    for name, src in programs.items():
        try:
            result = differential(src)
        except Exception as exc:                              # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if result['agree']:
            agreed += 1
        else:
            failures.append(f"{name}: interpreter={result['interpreter']} wasm={result['wasm']}")
    return agreed, len(programs), failures


if __name__ == '__main__':
    from svl.differential_exec import run_suite as _run  # noqa: F811
    import tests.test_svl_differential as suite
    ok, total, failures = _run(suite.PROGRAMS)
    print(f"{ok}/{total} programs agree")
    for line in failures:
        print(" ", line)
