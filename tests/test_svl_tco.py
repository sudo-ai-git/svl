"""Tail-call optimization: wired into the backend, verified by execution.

`return_call` reuses the caller's frame, so a tail-recursive call must complete at a
depth where the non-tail form traps with stack exhaustion. The signature guard is also
tested: a non-tail call must NOT be rewritten.
"""
import pytest

from tests.conftest import run_main
from svl.compiler_wasm import compile_file_to_wasm

TAIL_SRC = """
module t {
  func fact(n: int, acc: int) type int {
    if n == 0 then { return acc }
    else { return fact(n - 1, n * acc) }
  }
  func main() type int { return fact(20000, 1) }
}
"""

NON_TAIL_SRC = """
module t {
  func fact(n: int) type int {
    if n <= 1 then { return 1 }
    else { return n * fact(n - 1) }
  }
  func main() type int { return fact(10) }
}
"""


def test_tail_call_is_emitted():
    wat = compile_file_to_wasm(TAIL_SRC)
    assert "return_call" in wat


def test_non_tail_call_is_not_rewritten():
    wat = compile_file_to_wasm(NON_TAIL_SRC)
    assert "return_call" not in wat


def test_tail_recursion_runs_at_depth(wasmtime_module):
    assert run_main(wasmtime_module, compile_file_to_wasm(TAIL_SRC)) == 0   # i32 wrap


def test_non_tail_recursion_still_works_at_normal_depth(wasmtime_module):
    assert run_main(wasmtime_module, compile_file_to_wasm(NON_TAIL_SRC)) == 3628800


def test_signature_mismatch_falls_back(wasmtime_module):
    """A tail call whose callee signature differs must use a plain call."""
    src = """
module t {
  func g(x: int, y: int) type int { return x }
  func f(n: int) type int { return g(n, 1) }
  func main() type int { return f(5) }
}
"""
    wat = compile_file_to_wasm(src)
    assert "return_call" not in wat
    assert run_main(wasmtime_module, wat) == 5
