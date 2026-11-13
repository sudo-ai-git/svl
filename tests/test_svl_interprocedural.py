"""P2.3 — interprocedural return summaries.

The interval analyser used to return TOP for every call, so `let n = f(4)` lost all
precision and a provable out-of-bounds index after a call was invisible.  Calls are now
specialised under the ACTUAL argument intervals (an over-approximation, recursion-guarded).
"""
import pytest

from svl.compiler_wasm import compile_file_to_wasm
from svl.verify_gate import SVLVerificationError, verify_program

_LIB = "func f(x: int) type int { return x + 1 }"


def _program(call: str, length: int = 5) -> str:
    return (f"module m {{ {_LIB} func main() type int {{ let a = {list(range(length))} "
            f"let n = {call} return a[n] }} }}")


def test_call_argument_interval_is_propagated():
    """f(4) = [5,5]; a has length 5, so a[5] is provably out of bounds."""
    with pytest.raises(SVLVerificationError, match="out-of-bounds"):
        compile_file_to_wasm(_program("f(4)"))


def test_in_range_call_argument_stays_silent():
    """f(3) = [4,4]; a[4] is valid for a length-5 array."""
    assert verify_program(_program("f(3)")) == []
    compile_file_to_wasm(_program("f(3)"))


def test_zero_argument_stays_silent():
    assert verify_program(_program("f(0)")) == []


def test_recursive_function_does_not_diverge():
    """A (direct or indirect) recursion must fall back to TOP, not loop forever."""
    src = ("module m { func fib(n: int) type int { if n < 2 then { return n } else { } "
           "return fib(n-1) + fib(n-2) } func main() type int { return fib(8) } }")
    assert verify_program(src) == []


def test_nonlinear_return_is_summarised():
    """f(x) = x*x with x=[4,4] gives [16,16] — still a provable OOB."""
    src = ("module m { func f(x: int) type int { return x * x } "
           "func main() type int { let a = [1,2,3] let n = f(4) return a[n] } }")
    with pytest.raises(SVLVerificationError, match="out-of-bounds"):
        compile_file_to_wasm(src)
