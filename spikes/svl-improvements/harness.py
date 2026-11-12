#!/usr/bin/env python3
"""Shared helpers for the SVL improvement spikes.

Every spike is a throwaway experiment: it prototypes one proposed improvement
(monkeypatching the real compiler where possible, or a standalone AST pass),
runs the Given/When/Then, and prints a verdict.  Nothing here modifies the repo.
"""
import os
import sys

ROOT = "/home/sudosudo/.openclaw/workspace"
sys.path.insert(0, ROOT)

import wasmtime  # noqa: E402

from svl.compiler_wasm import compile_file_to_wasm  # noqa: E402
from svl.lexer import tokenize  # noqa: E402
from svl.parser_rd import parse  # noqa: E402


def run_wat(wat, export=None):
    """Assemble + VALIDATE + instantiate + run. Returns (rv, printed_bytes)."""
    binary = wasmtime.wat2wasm(wat)
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, binary)          # validation gate
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    i32 = wasmtime.ValType.i32()
    out = bytearray()
    memory = {}

    def read_mem(p, n):
        if "m" not in memory or p < 0 or n < 0:
            return b""
        return bytes(memory["m"].read(store, p, p + n))

    linker.define_func("env", "print", wasmtime.FuncType([i32, i32], []),
                       lambda p, n: out.extend(read_mem(p, n)))
    linker.define_func("env", "print_int", wasmtime.FuncType([i32], []),
                       lambda v: out.extend(str(v).encode()))
    linker.define_func("env", "putc", wasmtime.FuncType([i32], []),
                       lambda c: out.append(c & 0xFF))
    linker.define_func("env", "clear", wasmtime.FuncType([], []), lambda: None)
    linker.define_func("env", "malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20)
    linker.define_func("env", "iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0)
    linker.define_func("env", "await", wasmtime.FuncType([i32], [i32]), lambda x: x)
    inst = linker.instantiate(store, module)
    ex = inst.exports(store)
    names = [e.name for e in module.exports]
    if "memory" in names:
        memory["m"] = ex["memory"]
    if export is None:
        export = next((n for n in names if n.endswith("_main")), None)
    return ex[export](store), bytes(out)


def run_src(src, export=None):
    return run_wat(compile_file_to_wasm(src), export=export)


def parse_src(src):
    return parse(tokenize(src))


def verdict(name, passed, detail):
    mark = "VALIDATED" if passed else "INVALIDATED"
    print(f"[{name}] {mark}: {detail}")
    return 0 if passed else 1
