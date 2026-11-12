#!/usr/bin/env python3
"""Compile and RUN an SVL example in wasmtime.

    python3 examples/run_example.py examples/sieve.svl

Prints whatever the program wrote via `print`/`print_int`, then its return value.
This also documents the host ABI the backend expects:

    env.print(ptr: i32, len: i32)          -- write len bytes at ptr to stdout
    env.print_int(value: i32)              -- write the decimal value
    env.malloc(size: i32) -> i32           -- optional; programs use the internal allocator
    env.iterator_next(handle: i32) -> i32  -- only for `for x in <iterator>`
    env.await(value: i32) -> i32

Only the imports a program actually calls are emitted, so a host may provide just those.
The export is named `<module>_main`.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, ".."))          # the svl package when in-tree

import wasmtime                                        # noqa: E402
from svl.compiler_wasm import compile_file_to_wasm     # noqa: E402


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = argv[1]
    src = open(path).read()

    wat = compile_file_to_wasm(src)
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, wasmtime.wat2wasm(wat))
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)

    i32 = wasmtime.ValType.i32()
    out = bytearray()
    memory = {}

    def read_mem(ptr, n):
        mem = memory.get("m")
        if mem is None or ptr < 0 or n < 0:
            return b""
        return bytes(mem.read(store, ptr, ptr + n))

    linker.define_func("env", "print", wasmtime.FuncType([i32, i32], []),
                       lambda p, n: out.extend(read_mem(p, n)))
    linker.define_func("env", "print_int", wasmtime.FuncType([i32], []),
                       lambda v: out.extend(str(v).encode()))
    linker.define_func("env", "malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20)
    linker.define_func("env", "iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0)
    linker.define_func("env", "await", wasmtime.FuncType([i32], [i32]), lambda x: x)

    instance = linker.instantiate(store, module)
    exports = instance.exports(store)
    names = [e.name for e in module.exports]
    if "memory" in names:
        memory["m"] = exports["memory"]
    entry = next((n for n in names if n.endswith("_main")), None)
    if entry is None:
        print("no exported entry point (expected `<module>_main`)", file=sys.stderr)
        return 1

    rv = exports[entry](store)
    sys.stdout.write(out.decode("utf-8", "replace"))
    print(f"[{entry}() returned {rv}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
