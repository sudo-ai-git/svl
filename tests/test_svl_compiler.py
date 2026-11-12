"""Backend regressions: compile -> assemble -> RUN.

Text-level checks cannot see an invalid module. Every test here validates with
`wasmtime.Module` and invokes the exported `main`.
"""
import pytest

from tests.conftest import assemble, instantiate, run_main
from svl.compiler_wasm import compile_file_to_wasm


def test_while_loop_sum(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { let i = 0 let s = 0"
        " while i <= 5 { s += i i += 1 } return s } }")
    assert run_main(wasmtime_module, wat) == 15


def test_for_range_sum(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { let s = 0 for i in 0..5 { s += i } return s } }")
    assert run_main(wasmtime_module, wat) == 10


def test_if_expression(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { let c = 0"
        " let r = if c then 10 else 20 return r } }")
    assert run_main(wasmtime_module, wat) == 20


def test_assert_passes_when_true(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { let x = 5 assert x == 5 return 0 } }")
    assert run_main(wasmtime_module, wat) == 0


def test_assert_traps_when_false(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { let x = 5 assert x == 6 return 0 } }")
    with pytest.raises(Exception):
        run_main(wasmtime_module, wat)


def test_bitwise_operators_are_not_add(wasmtime_module):
    """`12 & 10` used to compile as `12 + 10` = 22."""
    wat = compile_file_to_wasm(
        "module m { func main() type int { return (12 & 10) + (1 | 2) } }")
    assert run_main(wasmtime_module, wat) == 11


def test_unary_minus(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { return -5 + 1 } }")
    assert run_main(wasmtime_module, wat) == -4


def test_array_read_write_and_len(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { let a: int = [3, 1, 2]"
        " a[0] = 9 return a[0] * 100 + len(a) } }")
    assert run_main(wasmtime_module, wat) == 903


def test_zeros_allocation(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { let a = zeros(4) a[3] = 7"
        " return a[3] * 10 + len(a) } }")
    assert run_main(wasmtime_module, wat) == 74


def test_struct_field_write(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { struct P { x: int  y: int }"
        " func main() type int { let p: P = P{x: 0, y: 0} p.x = 3 p.y = 4"
        " return p.x * 10 + p.y } }")
    assert run_main(wasmtime_module, wat) == 34


def test_match_expression(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type int { let x = 2"
        " let r = match x { case 1 => 10 case 2 => 20 case _ => 99 } return r } }")
    assert run_main(wasmtime_module, wat) == 20


def test_print_string(wasmtime_module):
    wat = compile_file_to_wasm(
        'module m { func main() type void { print("hi") return } }')
    module, engine = assemble(wasmtime_module, wat)
    instance, store, _ = instantiate(wasmtime_module, module, engine)
    instance.exports(store)["m_main"](store)      # must not trap


def test_const_and_var_globals(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { const N: int = 6 var counter: int = 1"
        " func main() type int { counter = counter + N return counter } }")
    assert run_main(wasmtime_module, wat) == 7


def test_void_function_has_no_result(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func nothing() type void { return }"
        " func main() type int { nothing() return 0 } }")
    assert "(func $m$nothing" in wat
    assert run_main(wasmtime_module, wat) == 0


def test_unknown_identifier_is_a_clean_compile_error():
    with pytest.raises(SyntaxError, match="Unknown identifier"):
        compile_file_to_wasm(
            "module m { func main() type int { return not_declared } }")


def test_out_of_range_literal_is_a_clean_compile_error():
    with pytest.raises(SyntaxError, match="out of i32 range"):
        compile_file_to_wasm(
            "module m { func main() type int { return 999999999999 } }")


def test_compound_assignment_on_a_global(wasmtime_module):
    """`var` is a WASM global: `counter += 1` must emit global.get/global.set."""
    wat = compile_file_to_wasm(
        "module m { var counter: int = 1 func main() type int {"
        " counter += 6 return counter } }")
    assert "global.get $counter" in wat
    assert "global.set $counter" in wat
    from tests.conftest import run_main
    assert run_main(wasmtime_module, wat) == 7


def test_compound_assignment_on_a_float(wasmtime_module):
    wat = compile_file_to_wasm(
        "module m { func main() type float { let x: float = 1.0 x += 2.5 return x } }")
    assert "f64.add" in wat
    from tests.conftest import run_main
    assert run_main(wasmtime_module, wat) == 3.5


def test_hebrew_and_ascii_compile_identically(wasmtime_module):
    """The 22-letter alias contract: same program, byte-identical WAT."""
    from svl.hebrew_alias import verify_alias
    src = ("module m { func main() type int { let x: int = 1"
           " let y: int = 2 return x + y } }")
    assert verify_alias(src)
    wat = compile_file_to_wasm(src)
    assert run_main(wasmtime_module, wat) == 3
