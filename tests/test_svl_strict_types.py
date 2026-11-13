"""P1.1 — the type checker is fail-closed in strict mode.

Before this, `_type_ann_to_type` fell back to `int` for every unrecognized annotation
kind and `_synth_ident` returned `void` for every unknown name, so `linear int`,
`{v: int | v > 0}` and `int & string` all compiled as plain `int` and an unknown
identifier was only caught later (and only when the expected type differed).

`strict=False` remains the documented escape hatch, so the lenient behaviour is
tested too — a gate that cannot be bypassed is not a gate, it is a wall.
"""
import pytest

from svl.compiler_wasm import compile_file_to_wasm
from svl.verify_gate import SVLVerificationError

UNSUPPORTED = {
    "intersection": "module t { func main() type int { let x: int & string = 5  return x } }",
}

# `linear` / `unique` are NOT unsupported any more: `svl/linear_regions.py` enforces
# the move discipline on the compile path, so both kinds are `enforced` in the feature
# registry.  A use is refused when the discipline is VIOLATED, which is a different
# message from "unsupported type annotation kind" — see tests/test_svl_linear_types.py.

# Refinement types are NOT unsupported any more: `svl/refinement_types.py` discharges
# their obligations on the compile path, so the kind is `enforced` in the feature
# registry.  A refinement is refused when its OBLIGATION is violated, which is a
# different message from "unsupported type annotation kind" — see
# tests/test_svl_refinement_types.py.


@pytest.mark.parametrize("kind", sorted(UNSUPPORTED))
def test_strict_refuses_unsupported_annotation(kind):
    with pytest.raises(SVLVerificationError, match="unsupported type annotation kind"):
        compile_file_to_wasm(UNSUPPORTED[kind])


@pytest.mark.parametrize("kind", sorted(UNSUPPORTED))
def test_lenient_still_compiles_unsupported_annotation(kind):
    """`strict=False` is the escape hatch and must keep working."""
    compile_file_to_wasm(UNSUPPORTED[kind], strict=False)


def test_strict_refuses_unknown_identifier():
    with pytest.raises(SVLVerificationError, match="unknown identifier 'not_declared'"):
        compile_file_to_wasm(
            "module m { func main() type int { return not_declared } }")


def test_strict_accepts_extern_ffi():
    """Externs live outside any module; they must be bound before the module body."""
    src = ('extern "c" func host_add(a: int, b: int) type int '
           'module m { func main() type int { return host_add(2, 3) } }')
    compile_file_to_wasm(src)


def test_strict_accepts_struct_field_access():
    """`s.x` parses as BinaryExpr('.', s, x): the right side is a field NAME."""
    src = ('module m { struct S { comparisons: int } '
           'func main() type int { let s: S = S{comparisons: 0} '
           's.comparisons += 5  return s.comparisons } }')
    compile_file_to_wasm(src)


def test_strict_accepts_for_in_loop_variable():
    """The loop variable must be bound, or every reference to it is unknown."""
    src = ('module m { func main() type int { let a = [1, 2, 3] let s = 0 '
           'for x in a { s += x } return s } }')
    compile_file_to_wasm(src)
