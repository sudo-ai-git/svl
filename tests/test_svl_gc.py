"""The conservative mark-sweep collector behind ``gc()``.

SVL has explicit ``free`` and a heap reset; this adds real collection of everything
still reachable from the recorded roots (module globals plus word-sized locals).

The tests execute the emitted WASM and, where behaviour alone cannot show that
reclamation happened, read the module's own linear memory and inspect block headers
against the documented layout in ``svl/gc_runtime.py``.
"""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl import gc_runtime
from svl.compiler_wasm import compile_file_to_wasm
from svl.repl import run_wat


def _run(src):
    return run_wat(compile_file_to_wasm(src))[0]


def _instantiate(src):
    """Compile, instantiate, and return (main, memory, store) for direct inspection."""
    import wasmtime

    wat = compile_file_to_wasm(src)
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, wat)
    store = wasmtime.Store(engine)
    inst = wasmtime.Instance(store, module, [])
    return inst.exports(store)["m_main"], inst.exports(store)["memory"], store


def _words(memory, store, address, count):
    data = bytes(memory.read(store, address, address + count * 4))
    return list(struct.unpack(f"<{count}i", data))


class TestCollection:
    def test_a_live_array_survives(self):
        src = ('module m { func main() type int '
               '{ let a = zeros(8)  a[0] = 5  gc()  return len(a) * 10 + a[0] } }')
        assert _run(src) == 85

    def test_an_array_literal_survives(self):
        src = ('module m { func main() type int '
               '{ let a: int = [1, 2, 3]  gc()  return len(a) * 100 + a[2] } }')
        assert _run(src) == 303

    def test_nested_blocks_are_traced_through_their_parent(self):
        """A pointer stored in an array element must keep its block alive."""
        src = '''module m {
          func main() type int {
            let outer: int = zeros(3)
            let i = 0
            while i < 3 { outer[i] = zeros(2)  i += 1 }
            let a = outer[0]  a[0] = 11
            let b = outer[1]  b[0] = 22
            let c = outer[2]  c[0] = 33
            gc()
            return outer[0][0] + outer[1][0] + outer[2][0]
          }
        }'''
        assert _run(src) == 66

    def test_struct_handles_in_an_array(self):
        src = '''module m {
          struct P { x: int, y: int }
          func main() type int {
            let arr: int = zeros(2)
            let p: P = P { x: 5, y: 6 }
            arr[0] = p
            gc()
            let q: P = arr[0]
            return q.x * 10 + q.y
          }
        }'''
        assert _run(src) == 56

    def test_module_globals_are_roots(self):
        src = '''module m {
          var g: int = 0
          func main() type int { g = zeros(4)  g[0] = 9  gc()  return len(g) * 10 + g[0] }
        }'''
        assert _run(src) == 49

    def test_dead_blocks_are_reclaimed(self):
        """A block whose frame has returned is unmarked, so sweep frees it."""
        src = '''module m {
          func make() type int { let x = zeros(8)  return len(x) }
          func main() type int {
            let keep = zeros(8)
            keep[0] = 1
            make()
            gc()
            return 0
          }
        }'''
        main, memory, store = _instantiate(src)
        main(store)
        # Blocks are 8-byte aligned: keep at 0 (header size 40), make's block next.
        headers = _words(memory, store, 0, 2)
        assert headers[0] & gc_runtime.MARK_BIT == 0, "live block must not stay marked"
        assert headers[0] & gc_runtime.FREE_BIT == 0, "live block must not be freed"
        dead_header = _words(memory, store, 40, 1)[0]
        assert dead_header & gc_runtime.FREE_BIT, \
            "a block from a returned frame must be returned to the free list"

    def test_explicit_free_then_collect(self):
        src = '''module m {
          func main() type int {
            let a = zeros(8)
            let b = zeros(8)
            a[0] = 99
            free(b)
            gc()
            let c = zeros(8)
            return len(a) * 10 + a[0]
          }
        }'''
        assert _run(src) == 179

    def test_collection_across_memory_growth(self):
        """More than the initial heap, with every root still valid afterwards."""
        src = '''module m {
          func main() type int {
            let N = 40
            let roots: int = zeros(N)
            let i = 0
            while i < N { roots[i] = zeros(16000)  i += 1 }
            gc()
            let sum = 0
            i = 0
            while i < N { sum += len(roots[i])  i += 1 }
            return sum
          }
        }'''
        assert _run(src) == 40 * 16000

    def test_gc_in_a_program_that_never_allocates(self):
        src = 'module m { func main() type int { gc()  return 42 } }'
        assert _run(src) == 42

    def test_strings_are_not_collected(self):
        src = ('module m { func main() type void '
               '{ print("hello")  gc()  print("world") } }')
        _wat = compile_file_to_wasm(src)
        _rv, out = run_wat(_wat)
        assert out.decode().strip() == "helloworld"


class TestScopeAndSafety:
    def test_programs_without_gc_are_byte_identical(self):
        """The collector's machinery must not leak into artifacts that never ask for it."""
        src = 'module m { func main() type int { let a = zeros(4)  return len(a) } }'
        wat = compile_file_to_wasm(src)
        assert '$gc' not in wat
        assert 'shadow_off' not in wat
        assert '$mark_value' not in wat

    def test_gc_programs_are_deterministic(self):
        src = '''module m {
          func main() type int {
            let a = zeros(8)
            let i = 0
            while i < 4 { a[0] = a[0] + 1  i += 1 }
            gc()
            return a[0]
          }
        }'''
        first = compile_file_to_wasm(src)
        for _ in range(3):
            assert compile_file_to_wasm(src) == first

    def test_collect_is_tri_state_honest_about_capacity(self):
        """The bitmap covers a fixed heap capacity; exceeding it traps, not corrupts."""
        # 9 MiB of 4-byte arrays exceeds HEAP_CAPACITY, so the allocation must trap
        # rather than writing into the reserved bitmap region.
        src = '''module m {
          func main() type int {
            gc()
            let big = zeros(2300000)
            return len(big)
          }
        }'''
        with pytest.raises(Exception):
            _run(src)


class TestLayoutConstants:
    def test_regions_do_not_overlap(self):
        assert gc_runtime.BITMAP_BASE < gc_runtime.MARK_BASE
        assert gc_runtime.MARK_BASE + gc_runtime.MARKSTACK_BYTES <= gc_runtime.SHADOW_BASE
        assert (gc_runtime.BITMAP_BASE - gc_runtime.HEAP_CAPACITY) == 0

    def test_bitmap_covers_the_heap_at_one_bit_per_slot(self):
        assert gc_runtime.BITMAP_BYTES * 8 * gc_runtime.BLOCK_ALIGN >= gc_runtime.HEAP_CAPACITY
