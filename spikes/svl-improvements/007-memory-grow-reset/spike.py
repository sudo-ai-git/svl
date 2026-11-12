#!/usr/bin/env python3
"""Spike 007: grow linear memory in $alloc and reset the heap between runs (F8)."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import run_wat, verdict                           # noqa: E402
import wasmtime                                               # noqa: E402
import svl.compiler_wasm as cw                                  # noqa: E402

_NEW_ALLOC = """(func $alloc (param $n i32) (result i32)
    (local $p i32)
    global.get $heap
    local.set $p
    local.get $p
    local.get $n
    i32.add
    memory.size
    i32.const 65536
    i32.mul
    i32.gt_u
    if
      local.get $p
      local.get $n
      i32.add
      memory.size
      i32.const 65536
      i32.mul
      i32.sub
      i32.const 65535
      i32.add
      i32.const 65536
      i32.div_u
      memory.grow
      i32.const -1
      i32.eq
      if
        unreachable
      end
    end
    global.get $heap
    local.get $n
    i32.add
    global.set $heap
    local.get $p
  )"""


def patch_wat(wat):
    """Replace $alloc with a growing version and reset the heap at main entry."""
    m = re.search(r"\(func \$alloc \(param \$n i32\) \(result i32\).*?\n  \)", wat, re.S)
    if not m:
        raise RuntimeError("$alloc not found")
    wat = wat[:m.start()] + _NEW_ALLOC + wat[m.end():]

    # heap reset function, inserted right before the exported main
    hm = re.search(r"\(global \$heap \(mut i32\) \(i32\.const (\d+)\)\)", wat)
    if not hm:
        raise RuntimeError("heap global not found")
    base = hm.group(1)
    reset = f"(func $heap_reset\n    i32.const {base}\n    global.set $heap\n  )"
    # insert the reset call at the top of the exported main body, AFTER the
    # (local ...) declarations (WASM requires locals to come first in a body)
    mm = re.search(
        r"(\(func \$[^\s]*main[^\s]* \(type \$t\d+\)[^\n]*\n)((?:    \(local [^\n]*\n)*)",
        wat)
    if not mm:
        raise RuntimeError("main func not found")
    insert_at = mm.end()
    wat = wat[:insert_at] + "    call $heap_reset\n" + wat[insert_at:]
    # insert the reset function just before main
    wat = wat[:mm.start()] + reset + "\n  " + wat[mm.start():]
    return wat


def main():
    # The real fix is now in the compiler (`$alloc` grows memory, `$heap_reset` runs at
    # main entry), so this spike validates the shipped behaviour directly instead of
    # monkeypatching the WAT.
    src = ("module m { func main() type int { let n = 100000"
           " let a = zeros(n) a[n - 1] = 1 return a[n - 1] } }")
    try:
        wat = cw.compile_file_to_wasm(src)
        binary = wasmtime.wat2wasm(wat)
        engine = wasmtime.Engine()
        module = wasmtime.Module(engine, binary)
        store = wasmtime.Store(engine)
        linker = wasmtime.Linker(engine)
        i32 = wasmtime.ValType.i32()
        for nm, sig, f in [
            ("print", wasmtime.FuncType([i32, i32], []), lambda a, b: None),
            ("print_int", wasmtime.FuncType([i32], []), lambda v: None),
            ("putc", wasmtime.FuncType([i32], []), lambda c: None),
            ("clear", wasmtime.FuncType([], []), lambda: None),
            ("malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20),
            ("iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0),
            ("await", wasmtime.FuncType([i32], [i32]), lambda x: x),
        ]:
            linker.define_func("env", nm, sig, f)
        inst = linker.instantiate(store, module)
        fn = inst.exports(store)["m_main"]
        rv1 = fn(store)
        rv2 = fn(store)                     # second call in the SAME store
        grow = "memory.grow" in wat
        ok = (rv1 == 1 and rv2 == 1 and grow)
        return verdict("007-memory-grow-reset", ok,
                       f"first={rv1}, second={rv2} (both must be 1); memory.grow present={grow}")
    except Exception as exc:
        return verdict("007-memory-grow-reset", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
