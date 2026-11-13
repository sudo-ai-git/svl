"""Linear and unique types — the static move discipline.

SVL has value semantics, so `linear`/`unique` are a STATIC discipline over variable
usage, the same shape as Rust's move checker:

  * a **move** is a bare variable where ownership transfers — the whole RHS of a
    `let`/assignment, an argument, or a `return` value;
  * a **use** is a variable inside a larger expression (`x + 1`, `f(x + 1)`).

A moved value may not be used or moved again.  An unconsumed `linear` variable is a
WARNING, not an error: a false positive would reject a correct program, which is
worse than the defect.  `unique` is affine, so an unconsumed one is not even a
warning.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.compiler_wasm import compile_file_to_wasm
from svl.feature_registry import ENFORCED, status_of, verify_registry
from svl.lexer import tokenize
from svl.linear_regions import (
    RegionInferenceEngine,
    _annotation_kind,
    check_function,
    check_linear_usage,
)
from svl.parser_rd import FuncDecl, parse
from svl.verify_gate import SVLVerificationError, verify_program


def _func(src):
    """The single FuncDecl in a one-function module."""
    ast = parse(tokenize(src))
    funcs = [n for n in _walk(ast) if isinstance(n, FuncDecl)]
    assert len(funcs) == 1, f"expected one function, got {len(funcs)}"
    return funcs[0]


def _walk(node, acc=None):
    if acc is None:
        acc = []
    if node is None:
        return acc
    if isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, acc)
        return acc
    if hasattr(node, '__dataclass_fields__'):
        acc.append(node)
        for f in node.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            _walk(getattr(node, f, None), acc)
    return acc


def _check(src):
    return check_linear_usage(parse(tokenize(src)))


class TestMoveDiscipline:
    def test_single_move_is_accepted(self):
        src = ('module m { func f() type int { let x: linear int = 5 '
               ' let y = x  return y } }')
        errors, _ = _check(src)
        assert errors == []
        assert verify_program(src) == []

    def test_double_move_is_refused(self):
        src = ('module m { func f() type int { let x: linear int = 5 '
               ' let y = x  let z = x  return z } }')
        errors, _ = _check(src)
        assert errors and "moved a second time" in errors[0]

    def test_double_move_is_refused_by_the_compile_path(self):
        src = ('module m { func f() type int { let x: linear int = 5 '
               ' let y = x  let z = x  return z } }')
        with pytest.raises(SVLVerificationError, match="moved a second time"):
            compile_file_to_wasm(src)

    def test_use_after_move_is_refused(self):
        src = ('module m { func f() type int { let x: linear int = 5 '
               ' let y = x  let z = x + 1  return z } }')
        errors, _ = _check(src)
        assert errors and "used after being moved" in errors[0]

    def test_borrow_then_move_is_accepted(self):
        """A use borrows; a later move is still allowed."""
        src = ('module m { func f() type int { let x: linear int = 5 '
               ' let y = x + 1  let z = x  return z } }')
        errors, _ = _check(src)
        assert errors == []

    def test_return_moves(self):
        src = 'module m { func f() type int { let x: linear int = 5  return x } }'
        assert _check(src)[0] == []

    def test_argument_moves(self):
        src = ('module m { func g(a: int) type int { return a } '
               ' func f() type int { let x: linear int = 5  return g(x) } }')
        assert _check(src)[0] == []

    def test_argument_used_twice_is_refused(self):
        src = ('module m { func g(a: int) type int { return a } '
               ' func f() type int { let x: linear int = 5 '
               ' let y = g(x)  let z = g(x)  return z } }')
        errors, _ = _check(src)
        assert errors and "moved a second time" in errors[0]

    def test_ownership_transfers_to_the_destination(self):
        """`let y = x` moves x and makes y the linear owner."""
        src = ('module m { func f() type int { let x: linear int = 5 '
               ' let y = x  let z = y  let w = y  return w } }')
        errors, _ = _check(src)
        assert errors and "'y' is moved a second time" in errors[0]

    def test_unique_shares_the_move_rules(self):
        src = ('module m { func f() type int { let x: unique int = 5 '
               ' let y = x  let z = x  return z } }')
        errors, _ = _check(src)
        assert errors and "moved a second time" in errors[0]


class TestNoFalsePositives:
    """Unannotated variables must be completely unaffected."""

    def test_unannotated_variables_may_be_reused(self):
        src = ('module m { func f() type int { let x = 5 '
               ' let y = x  let z = x  return z } }')
        errors, warnings = _check(src)
        assert errors == [] and warnings == []

    def test_unannotated_parameter_may_be_unused(self):
        """The region is linear, but the variable is not — it must not warn."""
        src = 'module m { func g(a: int) type int { return 1 } }'
        errors, warnings = _check(src)
        assert errors == [] and warnings == []

    def test_unannotated_local_alongside_a_linear_one_does_not_warn(self):
        """A linear variable in the same function must not condemn its neighbours."""
        src = ('module m { func f() type int { let x: linear int = 5 '
               ' let plain = 1  let y = x  return y + plain } }')
        _errors, warnings = _check(src)
        assert not any("plain" in w for w in warnings)

    def test_linear_function_with_no_linear_values_is_silent(self):
        src = 'module m { func f() type int { let a = 1  let b = 2  return a + b } }'
        assert _check(src) == ([], [])


class TestWarningsNotErrors:
    def test_unconsumed_linear_warns_but_does_not_refuse(self):
        src = 'module m { func g(x: linear int) type int { return 1 } }'
        errors, warnings = _check(src)
        assert errors == []
        assert warnings and "never consumed" in warnings[0]
        assert verify_program(src) == [], "a warning must not become a refusal"

    def test_unconsumed_unique_does_not_warn(self):
        """`unique` is affine: at most one use, not exactly one."""
        src = 'module m { func g(x: unique int) type int { return 1 } }'
        errors, warnings = _check(src)
        assert errors == [] and warnings == []

    def test_a_consumed_linear_does_not_warn(self):
        src = 'module m { func f() type int { let x: linear int = 5  return x } }'
        assert _check(src) == ([], [])


class TestEngineState:
    def test_annotation_kind_detects_both_kinds(self):
        fn = _func('module m { func f(a: linear int, b: unique int, c: int) '
                   ' type int { return c } }')
        assert _annotation_kind(fn.params[0].type_ann) == 'linear'
        assert _annotation_kind(fn.params[1].type_ann) == 'unique'
        assert _annotation_kind(fn.params[2].type_ann) is None

    def test_annotation_kind_does_not_match_by_substring(self):
        """The old check was `'linear' in str(ann).lower()` — a plain `int`
        annotation must never be mistaken for a linear one."""
        fn = _func('module m { func f(c: int) type int { return c } }')
        assert _annotation_kind(fn.params[0].type_ann) is None

    def test_stats_count_only_annotated_variables(self):
        """`get_stats` used to test `v.region.is_linear`, which is true for every
        variable in a function that has one linear value."""
        engine = RegionInferenceEngine()
        engine.enter_function('f')
        engine.declare_variable('lin', 'linear int', is_linear=True, kind='linear')
        engine.declare_variable('plain', 'int')
        stats = engine.get_stats()
        assert stats['total_variables'] == 2
        assert stats['linear_variables'] == 1

    def test_borrow_after_move_is_an_engine_error(self):
        engine = RegionInferenceEngine()
        engine.enter_function('f')
        engine.declare_variable('x', 'linear int', is_linear=True, kind='linear')
        engine.move_variable('x')
        assert engine.borrow_variable('x') is False
        assert any('already moved' in e for e in engine.errors)

    def test_check_function_entry_point(self):
        fn = _func('module m { func f() type int { let x: linear int = 5 '
                   ' let y = x  let z = x  return z } }')
        errors, _warnings = check_function(fn)
        assert errors and "moved a second time" in errors[0]


class TestRegistryAndStrict:
    def test_linear_and_unique_are_enforced(self):
        assert status_of('linear').status == ENFORCED
        assert status_of('unique').status == ENFORCED

    def test_registry_still_covers_every_kind(self):
        ok, unknown, failures = verify_registry()
        assert ok, f"unknown={unknown} failures={failures}"

    def test_strict_mode_no_longer_calls_linear_unsupported(self):
        src = 'module m { func f() type int { let x: linear int = 5  return x } }'
        compile_file_to_wasm(src)          # must not raise

    def test_lenient_mode_still_bypasses_the_gate(self):
        src = ('module m { func f() type int { let x: linear int = 5 '
               ' let y = x  let z = x  return z } }')
        compile_file_to_wasm(src, strict=False)
