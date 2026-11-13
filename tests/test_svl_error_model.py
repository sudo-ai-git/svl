"""P1.3 — the two-channel error model.

Channel 1, `raise`: `throw`/`catch` is an explicit, LEXICAL channel.  It cannot cross a
call boundary (`throw` outside a `try` is a compile error) and it carries the thrown
value's type, so `catch e` binds `e` to that type rather than to an opaque `Error`.

Channel 2, `trap`: runtime faults (out-of-bounds index, division by zero) are NOT
catchable.  Under strict mode the interval analyser refuses a `try` block containing a
provable trap, so `try { a[5] }` never compiles.
"""
import pytest

from tests.conftest import run_main
from svl.compiler_wasm import compile_file_to_wasm
from svl.verify_gate import SVLVerificationError


def test_throw_outside_try_is_refused():
    """`raise` cannot cross a call boundary: a callee's throw is a compile error."""
    src = ('module m { func f() type int { throw 1 } '
           'func main() type int { return f() } }')
    with pytest.raises(SyntaxError, match="throw` outside a `try"):
        compile_file_to_wasm(src)


def test_try_around_a_provable_trap_is_refused():
    """Traps are not catchable: the analyser refuses the try block outright."""
    src = ('module m { func main() type int { try { let a = [1,2,3] let i = 5 '
           'return a[i] } catch e { return 0 } } }')
    with pytest.raises(SVLVerificationError, match="out-of-bounds"):
        compile_file_to_wasm(src)


def test_catch_binds_the_thrown_type(wasmtime_module):
    """`catch e` binds the thrown value's type, so `return e` type-checks and runs."""
    src = 'module m { func main() type int { try { throw 7 } catch e { return e } } }'
    assert run_main(wasmtime_module, compile_file_to_wasm(src)) == 7


def test_catch_annotation_is_honoured(wasmtime_module):
    src = ('module m { func main() type int { try { throw 7 } '
           'catch e: int { return e } } }')
    assert run_main(wasmtime_module, compile_file_to_wasm(src)) == 7


def test_conflicting_throw_types_fall_back_to_error():
    """Mixed throw types make the channel ambiguous; the program still compiles."""
    src = ('module m { func main() type int { try { let c = 1 '
           'if c == 1 then { throw 1 } else { throw "x" } return 0 '
           '} catch e { return 0 } } }')
    compile_file_to_wasm(src)          # must not raise
