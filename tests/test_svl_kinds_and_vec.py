"""Kind correctness and `vec<T, n>` dependent bounds.

Two D2 engines wired in one pass:

  * `svl/kind_inference.py` — every application of a DECLARED type constructor must
    match its arity.  `type Box<a> = ...` gives Box kind `* -> *`, so `Box<int, int>`
    is ill-kinded and a bare `Box` names a constructor where a type is required.
  * `svl/vec_bounds.py` — `vec<T, n>` asserts the value has exactly n elements; when
    the bound and the initializer length are both literal they must agree.

Both decline rather than guess: an undeclared constructor, a symbolic size, or an
undeterminable initializer is silence, never a rejection.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.compiler_wasm import compile_file_to_wasm
from svl.feature_registry import ENFORCED, status_of, verify_registry
from svl.kind_inference import check_kind_correctness, collect_type_constructors
from svl.lexer import tokenize
from svl.parser_rd import parse
from svl.vec_bounds import check_vec_bounds, initializer_length
from svl.verify_gate import SVLVerificationError, verify_program


# ---------------------------------------------------------------------------
# Kind correctness
# ---------------------------------------------------------------------------

class TestKindCorrectness:
    def test_matching_arity_is_accepted(self):
        src = ('module m { type Box<a> = int  func f(x: Box<int>) type int '
               '{ return 0 } }')
        assert check_kind_correctness(parse(tokenize(src))) == []
        assert verify_program(src) == []

    def test_two_parameter_constructor(self):
        src = ('module m { type Pair<a, b> = int  func f(x: Pair<int, int>) '
               'type int { return 0 } }')
        assert check_kind_correctness(parse(tokenize(src))) == []

    def test_too_many_arguments_is_refused(self):
        src = ('module m { type Box<a> = int  func f(x: Box<int, int>) type int '
               '{ return 0 } }')
        problems = check_kind_correctness(parse(tokenize(src)))
        assert problems and "'Box' takes 1 type argument(s) but was given 2" in problems[0]

    def test_too_many_arguments_is_refused_by_the_compile_path(self):
        src = ('module m { type Box<a> = int  func f(x: Box<int, int>) type int '
               '{ return 0 } }')
        with pytest.raises(SVLVerificationError, match="type argument"):
            compile_file_to_wasm(src)

    def test_bare_constructor_is_refused(self):
        """`Box` alone names a `* -> *` thing where a type (`*`) is required."""
        src = 'module m { type Box<a> = int  func f(x: Box) type int { return 0 } }'
        problems = check_kind_correctness(parse(tokenize(src)))
        assert problems and "cannot be used as a type" in problems[0]

    def test_undeclared_constructor_is_not_guessed_at(self):
        """No declaration means no arity to check — silence, not a guess."""
        src = 'module m { func f(x: Option<int>) type int { return 0 } }'
        assert check_kind_correctness(parse(tokenize(src))) == []

    def test_a_real_struct_is_not_a_constructor(self):
        src = ('module m { struct P { x: int } func f(p: P) type int '
               '{ return p.x } }')
        assert check_kind_correctness(parse(tokenize(src))) == []

    def test_collects_arity_from_declarations(self):
        ast = parse(tokenize(
            'module m { type Box<a> = int  type Pair<a, b> = int }'))
        assert collect_type_constructors(ast) == {'Box': 1, 'Pair': 2}

    def test_constructor_kind_shape(self):
        from svl.kind_inference import constructor_kind
        assert repr(constructor_kind(0)) == '*'
        assert repr(constructor_kind(1)) == '(* -> *)'
        assert repr(constructor_kind(2)) == '(* -> (* -> *))'


# ---------------------------------------------------------------------------
# vec<T, n> bounds
# ---------------------------------------------------------------------------

class TestVecBounds:
    def test_matching_literal_array(self):
        src = ('module m { func f() type int { let v: vec<int, 3> = [1,2,3] '
               'return v[0] } }')
        assert check_vec_bounds(parse(tokenize(src))) == []
        assert verify_program(src) == []

    def test_mismatched_literal_array_is_refused(self):
        src = ('module m { func f() type int { let v: vec<int, 3> = [1,2] '
               'return v[0] } }')
        problems = check_vec_bounds(parse(tokenize(src)))
        assert problems and "has 2 element(s)" in problems[0]

    def test_mismatch_is_refused_by_the_compile_path(self):
        src = ('module m { func f() type int { let v: vec<int, 3> = [1,2] '
               'return v[0] } }')
        with pytest.raises(SVLVerificationError, match="vec<3>"):
            compile_file_to_wasm(src)

    def test_matching_zeros(self):
        src = ('module m { func f() type int { let v: vec<int, 3> = zeros(3) '
               'return v[0] } }')
        assert check_vec_bounds(parse(tokenize(src))) == []

    def test_mismatched_zeros(self):
        src = ('module m { func f() type int { let v: vec<int, 3> = zeros(2) '
               'return v[0] } }')
        assert check_vec_bounds(parse(tokenize(src)))

    def test_symbolic_size_is_silence(self):
        """A non-literal bound cannot be checked — decline, never guess."""
        src = ('module m { func f(n: int) type int { let v: vec<int, n> = [1,2,3] '
               'return v[0] } }')
        assert check_vec_bounds(parse(tokenize(src))) == []

    def test_undeterminable_initializer_is_silence(self):
        src = ('module m { func f(a: [int]) type int { let v: vec<int, 3> = a '
               'return v[0] } }')
        assert check_vec_bounds(parse(tokenize(src))) == []

    def test_initializer_length_helper(self):
        from svl.parser_rd import ArrayLit, CallExpr
        ast = parse(tokenize(
            'module m { func f() type int { let a = [1,2,3]  let b = zeros(4) '
            'let c = a  return 0 } }'))
        lets = [s for s in ast.modules[0].body.statements[0].body.statements
                if hasattr(s, 'value')]
        assert initializer_length(lets[0].value) == 3
        assert initializer_length(lets[1].value) == 4
        assert initializer_length(lets[2].value) is None

    def test_matching_nested_vec(self):
        src = ('module m { func h() type int { let v: vec<vec<int, 3>, 2> '
               '= [[1,2,3],[4,5,6]]  return v[0][0] } }')
        assert check_vec_bounds(parse(tokenize(src))) == []
        assert verify_program(src) == []

    def test_mismatched_nested_vec_element(self):
        src = ('module m { func h() type int { let v: vec<vec<int, 3>, 2> '
               '= [[1,2],[4,5,6]]  return v[0][0] } }')
        problems = check_vec_bounds(parse(tokenize(src)))
        assert problems and "an element has 2 element(s)" in problems[0]

    def test_mismatched_nested_vec_outer(self):
        src = ('module m { func h() type int { let v: vec<vec<int, 3>, 2> '
               '= [[1,2,3]]  return v[0][0] } }')
        problems = check_vec_bounds(parse(tokenize(src)))
        assert problems and "has 1 element(s)" in problems[0]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_vec_is_enforced(self):
        assert status_of('vec').status == ENFORCED

    def test_registry_still_covers_every_kind(self):
        ok, unknown, failures = verify_registry()
        assert ok, f"unknown={unknown} failures={failures}"

    def test_a_program_with_no_advanced_features_is_unaffected(self):
        src = 'module m { func f() type int { let a = [1,2,3]  return a[0] } }'
        assert verify_program(src) == []
