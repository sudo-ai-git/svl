"""Verification gates: the compile-time gate, the abstract interpreter, golden refs.

These are the checks that can actually FAIL, so they are tested in both directions:
a provable defect must be refused, and a correct program must stay silent.
"""
import pytest

from svl.compiler_wasm import compile_file_to_wasm
from svl.verify_gate import verify_program, SVLVerificationError


def test_provable_out_of_bounds_is_refused():
    src = ("module t { func main() type int { let a: int = [1, 2, 3]"
           " let i: int = 5 return a[i] } }")
    with pytest.raises(SVLVerificationError, match="out-of-bounds"):
        compile_file_to_wasm(src)


def test_provable_division_by_zero_is_refused():
    src = ("module t { func main() type int { let z: int = 0"
           " let a: int = 10 return a / z } }")
    with pytest.raises(SVLVerificationError):
        compile_file_to_wasm(src)


def test_correct_program_is_not_rejected():
    src = ("module t { func main() type int { let a: int = [1, 2, 3]"
           " let i: int = 1 return a[i] } }")
    assert verify_program(src) == []
    compile_file_to_wasm(src)


def test_strict_false_bypasses_the_gate():
    """`strict=False` is the documented escape hatch; the AI refusal is a gate, not a
    property of the backend."""
    src = ("module t { func main() type int { let a: int = [1, 2, 3]"
           " let i: int = 5 return a[i] } }")
    with pytest.raises(SVLVerificationError):
        compile_file_to_wasm(src)
    compile_file_to_wasm(src, strict=False)


def test_ast_guard_rejects_forbidden_calls():
    src = ("module t { func main() type void { let x: float = sum([1.0, 2.0])"
           " return } }")
    problems = verify_program(src)
    assert any("AST guard" in p for p in problems)


def test_golden_references_hold():
    from svl.golden_refs import verify_all_golden_refs
    results = verify_all_golden_refs()
    assert results and all(results.values()), results


def test_mod5_lattice_laws_hold():
    from svl.mod5_types import verify_mod5_lattice
    assert all(verify_mod5_lattice().values())


def test_hebrew_alias_contract():
    from svl.hebrew_alias import verify_mapping, verify_alias
    assert verify_mapping()
    src = ("module m { func main() type int { let x: int = 1"
           " let y: int = 2 return x + y } }")
    assert verify_alias(src)


def test_binary_ast_roundtrip():
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    from svl.serialization import to_binary, from_binary
    src = ("module m { func main() type int { let a: int = [1, 2]"
           " return a[0] + a[1] } }")
    ast = parse(tokenize(src))
    assert from_binary(to_binary(ast)) is not None
