#!/usr/bin/env python3
"""Run a playable SVL game (or any interactive SVL program) in wasmtime.

    python3 examples/run_snake.py examples/snake.svl            # turn-based: one key per move
    python3 examples/run_snake.py examples/snake.svl --timeout 0.15   # real-time
    printf 'ddddds' | python3 examples/run_snake.py examples/snake.svl   # scripted / replay

Keys for snake.svl: w a s d to steer, q to quit. (Keys are read raw on a terminal, so no
Enter needed.)

Host ABI used here (only the imports a program actually calls are emitted):

    env.putc(c: i32)                        -- write one byte
    env.print(ptr: i32, len: i32)           -- write len bytes at ptr
    env.print_int(v: i32)                   -- write the decimal value
    env.read_key() -> i32                   -- next byte, 0 = no key right now, -1 = EOF
    env.clear()                             -- reset the display (the host decides how)
    env.malloc/iterator_next/await          -- unused by the snake

`read_key` returning 0 for "nothing pressed" is what makes real-time play possible: the host
returns 0 on a timeout and the program simply advances a tick.
"""
import argparse
import os
import select
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

import wasmtime                                        # noqa: E402
from svl.compiler_wasm import compile_file_to_wasm     # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--timeout", type=float, default=0.0,
                    help="seconds to wait for a key; 0 = block until a key or EOF")
    ap.add_argument("--no-clear", action="store_true")
    args = ap.parse_args(argv[1:])

    src = open(args.path).read()
    wat = compile_file_to_wasm(src)
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, wasmtime.wat2wasm(wat))
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)
    i32 = wasmtime.ValType.i32()

    tty_in = sys.stdin.isatty()
    tty_out = sys.stdout.isatty()
    memory = {}
    out = sys.stdout

    # ---- input ---------------------------------------------------------------
    raw_saved = None
    if tty_in:
        import termios
        import tty
        fd = sys.stdin.fileno()
        raw_saved = termios.tcgetattr(fd)
        tty.setcbreak(fd)                              # keeps Ctrl-C working

    pending = bytearray()

    def read_key() -> int:
        if tty_in:
            if args.timeout > 0:
                r, _, _ = select.select([sys.stdin], [], [], args.timeout)
                if not r:
                    return 0                           # nothing pressed -> keep ticking
            ch = sys.stdin.read(1)
            return ord(ch) if ch else -1
        # piped/scripted: consume stdin one byte at a time
        if not pending:
            data = sys.stdin.buffer.read(1)
            if not data:
                return -1
            pending.extend(data)
        return pending.pop(0)

    def clear():
        if tty_out and not args.no_clear:
            out.write("\x1b[2J\x1b[H")
            out.flush()

    def read_mem(ptr, n):
        mem = memory.get("m")
        if mem is None or ptr < 0 or n < 0:
            return b""
        return bytes(mem.read(store, ptr, ptr + n))

    def emit(data: bytes):
        out.write(data.decode("utf-8", "replace"))
        out.flush()

    linker.define_func("env", "putc", wasmtime.FuncType([i32], []), lambda c: emit(bytes([c & 0xFF])))
    linker.define_func("env", "print", wasmtime.FuncType([i32, i32], []), lambda p, n: emit(read_mem(p, n)))
    linker.define_func("env", "print_int", wasmtime.FuncType([i32], []), lambda v: emit(str(v).encode()))
    linker.define_func("env", "read_key", wasmtime.FuncType([], [i32]), read_key)
    linker.define_func("env", "clear", wasmtime.FuncType([], []), clear)
    linker.define_func("env", "malloc", wasmtime.FuncType([i32], [i32]), lambda n: 1 << 20)
    linker.define_func("env", "iterator_next", wasmtime.FuncType([i32], [i32]), lambda h: 0)
    linker.define_func("env", "await", wasmtime.FuncType([i32], [i32]), lambda x: x)

    try:
        instance = linker.instantiate(store, module)
        exports = instance.exports(store)
        names = [e.name for e in module.exports]
        if "memory" in names:
            memory["m"] = exports["memory"]
        entry = next((n for n in names if n.endswith("_main")), None)
        if entry is None:
            print("no exported entry point (expected `<module>_main`)", file=sys.stderr)
            return 1
        score = exports[entry](store)
    finally:
        if raw_saved is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, raw_saved)

    print(f"\nGAME OVER  score={score}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(130)
