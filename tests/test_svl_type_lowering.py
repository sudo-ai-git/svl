"""Type-directed lowering: the type layer must change the emitted WASM.

Every test here is a regression for a defect that produced *silently wrong* output:
an un-annotated `let x = 1.5` used to emit an i32 local holding an f64 literal (the text
parsed, the module failed validation), and `x + y` on two floats emitted `i32.add`.
"""
import pytest

from svl.compiler_wasm import compile_file_to_wasm
from svl.lexer import tokenize
from svl.parser_rd import parse
from svl.type_lowering import infer_types, type_to_valtype


def test_unannotated_float_local_lowers_to_f64(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type float { let x = 1.5 return x } }")
    assert "(local $x f64)" in wat
    assert "f64.const 1.5" in wat
    from tests.conftest import run_main
    assert run_main(wasmtime_module, wat) == 1.5


def test_float_arithmetic_uses_f64_ops(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type float {"
        " let x: float = 1.5 let y: float = 2.5 return x + y } }")
    assert "f64.add" in wat
    assert "i32.add" not in wat
    from tests.conftest import run_main
    assert run_main(wasmtime_module, wat) == 4.0


def test_float_comparison_uses_f64_ops(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int {"
        " let x: float = 1.5 let y: float = 2.5"
        " if x < y then { return 1 } else { return 0 } } }")
    assert "f64.lt" in wat
    from tests.conftest import run_main
    assert run_main(wasmtime_module, wat) == 1


def test_float_negation_uses_f64_neg(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type float { let x: float = 1.5 return -x } }")
    assert "f64.neg" in wat
    from tests.conftest import run_main
    assert run_main(wasmtime_module, wat) == -1.5


def test_mixed_int_float_is_a_compile_error():
    with pytest.raises(SyntaxError, match="mixed int and float"):
        compile_file_to_wasm(
            "module m { func main() type float {"
            " let x: float = 1.5 let y: int = 2 return x + y } }")


def test_unannotated_parameter_is_in_the_signature(wasmtime_module):
    """Un-annotated params used to be dropped from the function type entirely."""
    wat = compile_file_to_wasm(
        "module m { func f(x) type int { return x }"
        " func main() type int { return f(7) } }")
    assert "(param $x i32)" in wat
    from tests.conftest import run_main
    assert run_main(wasmtime_module, wat) == 7


def test_struct_copy_resolves_through_inference(wasmtime_module):
    """`let q = p` must carry p's struct type with no annotation and no literal."""
    wat = compile_file_to_wasm(
        "module m { struct P { x: int  y: int }"
        " func main() type int { let p: P = P{x: 1, y: 2} let q = p return q.y } }")
    from tests.conftest import run_main
    assert run_main(wasmtime_module, wat) == 2


def test_inferred_types_are_recorded():
    src = ("module m { func main() type float {"
           " let x = 1.5 let y: float = 2.5 let z = x + y return z } }")
    result = infer_types(parse(tokenize(src)))
    assert result.ok, result.errors
    assert type_to_valtype(result.local_type("main", "x")) == "f64"
    assert type_to_valtype(result.local_type("main", "z")) == "f64"


def test_unknown_type_falls_back_to_previous_behaviour():
    """A type the checker cannot classify must not change codegen."""
    assert type_to_valtype(None) is None
    src = "module m { func f(a) type int { return a } func main() type int { return f(1) } }"
    result = infer_types(parse(tokenize(src)))
    # `a` is an un-annotated parameter: it gets a type variable, which lowers to i32
    assert type_to_valtype(result.local_type("f", "a")) is None


def test_compilation_is_deterministic():
    src = ("module m { func main() type float {"
           " let x = 1.5 let y: float = 2.5 return x + y } }")
    assert compile_file_to_wasm(src) == compile_file_to_wasm(src)
