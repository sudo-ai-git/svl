#!/usr/bin/env python3
"""Warm + cold in-process benchmark: non-foldable accumulation loop.

The first version of this benchmark used `while i < n { i += 1 }`, which rustc -O
replaced with `return n` -- the Rust "warm" number was a no-op.  This version
accumulates a value, and pins `n` with `black_box` / `volatile`, so no compiler
can fold the loop away.  SVL has no optimiser, so its number is honest by default.

    python3 bench2.py
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

N = 5_000_000


def _i32(v):
    v &= 0xFFFFFFFF
    return v - 2 ** 32 if v >= 2 ** 31 else v


def _expected():
    """xorshift32 accumulation -- cannot be constant-folded by any compiler."""
    x, s = 1, 0
    for _ in range(N):
        x = _i32(x ^ _i32(x << 13))
        x = _i32(x ^ (x >> 17))          # Python >> is arithmetic, like i32.shr_s
        x = _i32(x ^ _i32(x << 5))
        s = _i32(s + x)
    return s


EXPECTED = _expected()

SVL_SRC = f"""module loop {{
  func main() type int {{
    let n: int = {N}
    let x: int = 1
    let s: int = 0
    let i: int = 0
    while i < n {{
      x = x ^ (x << 13)
      x = x ^ (x >> 17)
      x = x ^ (x << 5)
      s = s + x
      i += 1
    }}
    return s
  }}
}}
"""

RUST_SRC = f"""
#![no_std]
#![no_main]
#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {{ loop {{}} }}
#[no_mangle]
pub extern "C" fn run() -> i32 {{
    let n: i32 = core::hint::black_box({N});
    let mut x: i32 = 1;
    let mut s: i32 = 0;
    let mut i: i32 = 0;
    while i < n {{
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        s = s.wrapping_add(x);
        i += 1;
    }}
    s
}}
"""

C_SRC = f"""
#include <stdio.h>
int main(void) {{ volatile int n = {N}; int x = 1; int s = 0;
  for (int i = 0; i < n; i++) {{ x ^= x << 13; x ^= x >> 17; x ^= x << 5; s += x; }}
  printf("%d\\n", s); return 0; }}
"""


def timeit(fn, k=7):
    ts = []
    for _ in range(k):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000.0)
    return min(ts), statistics.median(ts)


def linker_with_host(linker):
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


def svl_module():
    from svl.compiler_wasm import compile_file_to_wasm
    t0 = time.perf_counter()
    wat = compile_file_to_wasm(SVL_SRC)
    compile_ms = (time.perf_counter() - t0) * 1000.0
    return wasmtime.wat2wasm(wat), compile_ms


def rust_module():
    src = os.path.join(HERE, "loop.rs")
    out = os.path.join(HERE, "loop.wasm")
    open(src, "w").write(RUST_SRC)
    t0 = time.perf_counter()
    p = subprocess.run(["rustc", "--target", "wasm32-unknown-unknown", "-O", "-o", out, src],
                       capture_output=True, text=True)
    compile_ms = (time.perf_counter() - t0) * 1000.0
    assert p.returncode == 0, p.stderr
    return open(out, "rb").read(), compile_ms


def instantiate(binary):
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, binary)
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    linker_with_host(linker)
    return module, store, linker.instantiate(store, module)


def main():
    print("=" * 78)
    print(f"BENCHMARK — xorshift32 accumulation over {N} iterations, expected {EXPECTED}")
    print("=" * 78)
    rows = []

    # SVL
    binary, compile_ms = svl_module()
    module, store, inst = instantiate(binary)
    fn = inst.exports(store)[next(e.name for e in module.exports if e.name.endswith("_main"))]
    warm, wmed = timeit(lambda: fn(store))
    # cold: a FRESH instance per run (SVL's allocator state forces this)
    def cold():
        _, _, i2 = instantiate(binary)
        f2 = i2.exports(store)[next(e.name for e in module.exports if e.name.endswith("_main"))]
        return f2(store)
    cold_ms, cmed = timeit(cold)
    rows.append(("SVL", "wasm/wasmtime", compile_ms, warm, wmed, cold_ms, len(binary), fn(store)))

    # Rust wasm
    binary, compile_ms = rust_module()
    module, store, inst = instantiate(binary)
    fn = inst.exports(store)["run"]
    warm, wmed = timeit(lambda: fn(store))
    def cold_r():
        _, _, i2 = instantiate(binary)
        return i2.exports(store)["run"](store)
    cold_ms, cmed = timeit(cold_r)
    rows.append(("Rust", "wasm/wasmtime", compile_ms, warm, wmed, cold_ms, len(binary), fn(store)))

    # C native
    src = os.path.join(HERE, "loop.c")
    out = os.path.join(HERE, "loop.c.bin")
    open(src, "w").write(C_SRC)
    t0 = time.perf_counter()
    p = subprocess.run(["gcc", "-O2", "-o", out, src], capture_output=True, text=True)
    c_compile = (time.perf_counter() - t0) * 1000.0
    assert p.returncode == 0, p.stderr
    best, med = timeit(lambda: subprocess.run([out], capture_output=True, text=True))
    rows.append(("C", "native/x86-64", c_compile, best, med, best, os.path.getsize(out), 0))

    for name, target, c, w, wm, cm, sz, r in rows:
        print(f"{name:<6} {target:<16} compile={c:>8.1f} ms  warm={w:>8.3f} ms "
              f"({wm:.3f} med)  cold={cm:>8.3f} ms  artifact={sz} B  result={r}")
    print("-" * 78)
    print(f"expected result: {EXPECTED}")
    print("note: native 'warm' pays process spawn; wasm 'cold' pays module compile+instantiate.")


if __name__ == "__main__":
    sys.exit(main())
