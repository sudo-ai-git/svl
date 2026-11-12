#!/usr/bin/env python3
"""Spike 010: minimal throw/try error model via a per-try error flag (F9).

Validates the exact WASM lowering the panel proposed: a `block $try` around the try body,
an `err` local set by `throw`, and a branch that binds the catch variable when err != 0.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402
import wasmtime                                               # noqa: E402

# try { throw 7 } catch e { r = e }  ->  r must be 7
WAT_THROW = """(module
  (func (export "f") (result i32)
    (local $err i32) (local $r i32)
    block $try
      i32.const 7
      local.set $err
      br $try
    end
    local.get $err
    if
      local.get $err
      local.set $r
    end
    local.get $r
  ))"""

# try { let x = 1 } catch e { r = e }  ->  no throw, r stays 0
WAT_NO_THROW = """(module
  (func (export "f") (result i32)
    (local $err i32) (local $r i32)
    block $try
      i32.const 0
      local.set $err
      br $try
    end
    local.get $err
    if
      local.get $err
      local.set $r
    end
    local.get $r
  ))"""


def run(wat):
    binary = wasmtime.wat2wasm(wat)
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, binary)
    store = wasmtime.Store(engine)
    inst = wasmtime.Linker(engine).instantiate(store, module)
    return inst.exports(store)["f"](store)


def main():
    try:
        rv_throw = run(WAT_THROW)
        rv_no = run(WAT_NO_THROW)
        ok = (rv_throw == 7 and rv_no == 0)
        return verdict("010-try-catch-error-model", ok,
                       f"throw landed in catch = {rv_throw} (want 7); "
                       f"no-throw skipped catch = {rv_no} (want 0)")
    except Exception as exc:
        return verdict("010-try-catch-error-model", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
