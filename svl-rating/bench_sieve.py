#!/usr/bin/env python3
"""Measured cross-language benchmark: sieve of Eratosthenes, N = 100000.

Two apples-to-apples axes:
  * WASM-in-wasmtime: SVL (WAT->wasm) vs Rust (wasm32-unknown-unknown, no imports)
  * native:           C (gcc -O2), Rust (rustc -O), Python 3

Every number below is produced by a timed run in this session; nothing is
copied from a doc.  `best of K` for run time.
"""
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/sudosudo/.openclaw/workspace"
sys.path.insert(0, ROOT)

import wasmtime  # noqa: E402


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def timeit(fn, k=5):
    ts = []
    for _ in range(k):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000.0)
    return min(ts), statistics.median(ts)


def run_svl():
    from svl.compiler_wasm import compile_file_to_wasm
    src = open(os.path.join(HERE, "sieve.svl")).read()

    t0 = time.perf_counter()
    wat = compile_file_to_wasm(src)
    compile_ms = (time.perf_counter() - t0) * 1000.0
    binary = wasmtime.wat2wasm(wat)

    def fresh():
        """A FRESH instance per run: SVL's bump allocator never frees, so a
        second call in the same instance leaks past the 1 MiB ceiling."""
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, binary)
        store = wasmtime.Store(engine)
        linker = wasmtime.Linker(engine)
        i32 = wasmtime.ValType.i32()
        for name, sig, f in [
            ("print", wasmtime.FuncType([i32, i32], []), lambda a, b: None),
            ("print_int", wasmtime.FuncType([i32], []), lambda v: None),
            ("putc", wasmtime.FuncType([i32], []), lambda c: None),
            ("clear", wasmtime.FuncType([], []), lambda: None),
            ("malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20),
            ("iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0),
            ("await", wasmtime.FuncType([i32], [i32]), lambda x: x),
        ]:
            linker.define_func("env", name, sig, f)
        inst = linker.instantiate(store, module)
        entry = next(e.name for e in module.exports if e.name.endswith("_main"))
        return inst.exports(store)[entry](store)

    best, med = timeit(fresh)
    return {"compile_ms": compile_ms, "run_ms": best, "run_med": med,
            "bytes": len(binary), "result": fresh()}


def run_rust_wasm():
    src = os.path.join(HERE, "sieve.rs")
    out = os.path.join(HERE, "sieve.wasm")
    t0 = time.perf_counter()
    p = sh(["rustc", "--target", "wasm32-unknown-unknown", "-O", "-o", out, src])
    compile_ms = (time.perf_counter() - t0) * 1000.0
    assert p.returncode == 0, p.stderr
    binary = open(out, "rb").read()

    def fresh():
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, binary)
        store = wasmtime.Store(engine)
        linker = wasmtime.Linker(engine)
        i32 = wasmtime.ValType.i32()
        for name, sig, f in [
            ("print", wasmtime.FuncType([i32, i32], []), lambda a, b: None),
            ("print_int", wasmtime.FuncType([i32], []), lambda v: None),
            ("putc", wasmtime.FuncType([i32], []), lambda c: None),
            ("clear", wasmtime.FuncType([], []), lambda: None),
            ("malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20),
            ("iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0),
            ("await", wasmtime.FuncType([i32], [i32]), lambda x: x),
        ]:
            linker.define_func("env", name, sig, f)
        inst = linker.instantiate(store, module)
        return inst.exports(store)["sieve"](store)

    best, med = timeit(fresh)          # cold: fresh module + instance, like SVL
    return {"compile_ms": compile_ms, "run_ms": best, "run_med": med,
            "bytes": len(binary), "result": fresh()}


def run_c_native():
    src = os.path.join(HERE, "sieve.c")
    out = os.path.join(HERE, "sieve_c")
    t0 = time.perf_counter()
    p = sh(["gcc", "-O2", "-o", out, src])
    compile_ms = (time.perf_counter() - t0) * 1000.0
    assert p.returncode == 0, p.stderr

    def go():
        return int(sh([out]).stdout.strip())

    best, med = timeit(go)
    return {"compile_ms": compile_ms, "run_ms": best, "run_med": med,
            "bytes": os.path.getsize(out), "result": go()}


def run_rust_native():
    src = os.path.join(HERE, "sieve_native.rs")
    out = os.path.join(HERE, "sieve_rust")
    t0 = time.perf_counter()
    p = sh(["rustc", "-O", "-o", out, src])
    compile_ms = (time.perf_counter() - t0) * 1000.0
    assert p.returncode == 0, p.stderr

    def go():
        return int(sh([out]).stdout.strip())

    best, med = timeit(go)
    return {"compile_ms": compile_ms, "run_ms": best, "run_med": med,
            "bytes": os.path.getsize(out), "result": go()}


def run_python():
    src = os.path.join(HERE, "sieve.py")
    code = compile(open(src).read(), src, "exec")
    ns = {}

    def go():
        exec(code, ns)
        return ns["result"]

    best, med = timeit(go)
    return {"compile_ms": 0.0, "run_ms": best, "run_med": med,
            "bytes": os.path.getsize(src), "result": go()}


def main():
    print("=" * 78)
    print("MEASURED BENCHMARK — sieve(100000), best-of-5 run time (ms)")
    print("=" * 78)
    rows = []
    for name, fn, target in [
        ("SVL", run_svl, "wasm/wasmtime"),
        ("Rust", run_rust_wasm, "wasm/wasmtime"),
        ("C", run_c_native, "native/x86-64"),
        ("Rust", run_rust_native, "native/x86-64"),
        ("Python", run_python, "native/x86-64"),
    ]:
        r = fn()
        rows.append((name, target, r))
        print(f"{name:<8} {target:<16} result={r['result']:<8} "
              f"compile={r['compile_ms']:>8.1f} ms  run={r['run_ms']:>8.2f} ms  "
              f"({r['run_med']:.2f} med)  artifact={r['bytes']} B")
    print("-" * 78)
    ref = rows[0][2]["result"]
    same = all(r["result"] == ref for _, _, r in rows)
    print(f"all results identical: {same} (value {ref})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
