"""Refinement types `{ v: T | P(v) }` — introduction and elimination.

`svl/refinement_types.py` discharges refinement obligations through Z3 on the compile
path.  The semantics under test:

  * **Introduction (must prove)** — `let x: {v: T | P} = e`, a call to a refined
    parameter, and a `return` against a refined result all carry an obligation.
  * **Elimination (may assume)** — a proven binding may be used as an assumption
    later; a refined parameter is assumed inside its body.

The gates that matter are the two directions: a violated obligation MUST be refused,
and a satisfied one MUST stay silent.  A false positive rejects a correct program,
which is worse than the defect being checked for.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.compiler_wasm import compile_file_to_wasm
from svl.feature_registry import ENFORCED, status_of, verify_registry
from svl.lexer import tokenize
from svl.parser_rd import parse
from svl.refinement_types import check_refinements, extract
from svl.verify_gate import SVLVerificationError, verify_program

z3 = pytest.importorskip("z3")


def _engine(src):
    return check_refinements(parse(tokenize(src)))


def _gate(src):
    return verify_program(src)


class TestIntroduction:
    def test_satisfied_let_is_accepted(self):
        src = 'module m { func f() type int { let x: { v: int | v > 0 } = 5  return x } }'
        assert _engine(src) == []
        assert _gate(src) == []

    def test_violated_let_is_refused(self):
        src = 'module m { func f() type int { let x: { v: int | v > 0 } = -5  return x } }'
        problems = _engine(src)
        assert problems and "refinement on 'x'" in problems[0]
        assert any('refinement' in p for p in _gate(src))

    def test_violated_let_is_refused_by_the_compile_path(self):
        src = 'module m { func f() type int { let x: { v: int | v > 0 } = -5  return x } }'
        with pytest.raises(SVLVerificationError, match="refinement"):
            compile_file_to_wasm(src)

    def test_arithmetic_value_is_modelled(self):
        """The obligation is on the VALUE EXPRESSION, not just literals."""
        ok = 'module m { func f() type int { let x: { v: int | v > 0 } = 2 + 3  return x } }'
        bad = 'module m { func f() type int { let x: { v: int | v > 0 } = 2 - 3  return x } }'
        assert _engine(ok) == []
        assert _engine(bad)

    def test_call_argument_obligation_is_refused(self):
        src = ('module m { func g(x: { v: int | v > 0 }) type int { return x } '
               ' func f() type int { return g(0 - 1) } }')
        assert _engine(src) and any('call to' in p for p in _gate(src))

    def test_call_argument_obligation_is_accepted(self):
        src = ('module m { func g(x: { v: int | v > 0 }) type int { return x } '
               ' func f() type int { return g(7) } }')
        assert _engine(src) == []

    def test_call_in_a_let_value_is_checked(self):
        src = ('module m { func g(x: { v: int | v > 0 }) type int { return x } '
               ' func f() type int { let y: int = g(0 - 2)  return y } }')
        assert _engine(src)

    def test_refined_return_is_refused(self):
        src = 'module m { func f() type { v: int | v > 0 } { return 0 - 3 } }'
        assert _engine(src) and any('return does not satisfy' in p for p in _gate(src))

    def test_refined_return_is_accepted(self):
        src = 'module m { func f() type { v: int | v > 0 } { return 3 } }'
        assert _engine(src) == []


class TestElimination:
    def test_refined_parameter_is_assumed_inside_the_body(self):
        """`x: {v: int | v > 0}` gives `x > 0` for free in the body."""
        src = ('module m { func g(x: { v: int | v > 0 }) type int '
               '{ let y: { v: int | v > 0 } = x  return y } }')
        assert _engine(src) == []

    def test_weaker_predicate_follows_from_a_stronger_one(self):
        src = ('module m { func g(x: { v: int | v > 5 }) type int '
               '{ let y: { v: int | v > 3 } = x  return y } }')
        assert _engine(src) == []

    def test_stronger_predicate_does_not_follow_from_a_weaker_one(self):
        """x > 0 does not prove x > 3 — the counterexample is x = 1."""
        src = ('module m { func g(x: { v: int | v > 0 }) type int '
               '{ let y: { v: int | v > 3 } = x  return y } }')
        problems = _engine(src)
        assert problems and "x=1" in problems[0]

    def test_refined_return_uses_the_assumed_parameter(self):
        src = ('module m { func g(x: { v: int | v > 0 }) type { v: int | v > 0 } '
               '{ return x } }')
        assert _engine(src) == []

    def test_transitivity_through_a_proven_let(self):
        src = ('module m { func f() type int { let x: { v: int | v > 0 } = 5 '
               ' let y: { v: int | v > 3 } = x  return y } }')
        assert _engine(src) == []


class TestDeclineNotAssume:
    def test_unmodelled_operator_is_silence(self):
        """`/` is declined — never discharged, never a false positive."""
        src = 'module m { func f() type int { let x: { v: int | v / 2 > 0 } = 5  return x } }'
        assert _engine(src) == []
        assert _gate(src) == []

    def test_unmodelled_call_in_a_predicate_is_silence(self):
        src = ('module m { func h() type int { return 1 } '
               ' func f() type int { let x: { v: int | v > h() } = 5  return x } }')
        assert _engine(src) == []

    def test_unmodelled_value_is_silence(self):
        src = 'module m { func f(a: [int]) type int { let x: { v: int | v > 0 } = a[0]  return x } }'
        assert _engine(src) == []

    def test_unrefined_parameter_is_not_assumed_positive(self):
        """`x: int` gives no assumption — producing a positive value needs a proof."""
        src = 'module m { func f(x: int) type int { let y: { v: int | v > 0 } = x  return y } }'
        assert _engine(src)

    def test_float_refinement_is_declined(self):
        """Only int/bool bases are modelled; a float refinement is not guessed at."""
        ann = parse(tokenize(
            'module m { func f(x: { v: float | v > 0 }) type int { return 0 } }'))
        funcs = [n for n in _walk(ann) if hasattr(n, 'params') and n.params]
        assert funcs
        assert extract(funcs[0].params[0].type_ann) is None


class TestRegistryAndStrict:
    def test_refinement_is_registered_as_enforced(self):
        assert status_of('refinement').status == ENFORCED

    def test_registry_still_covers_every_kind(self):
        ok, unknown, failures = verify_registry()
        assert ok, f"unknown={unknown} failures={failures}"

    def test_strict_mode_no_longer_calls_it_unsupported(self):
        """The kind is enforced, so the old 'unsupported annotation' error is gone."""
        src = 'module m { func f() type int { let x: { v: int | v > 0 } = 5  return x } }'
        compile_file_to_wasm(src)          # must not raise

    def test_lenient_mode_still_bypasses_the_gate(self):
        src = 'module m { func f() type int { let x: { v: int | v > 0 } = -5  return x } }'
        compile_file_to_wasm(src, strict=False)


class TestExtract:
    def test_non_refinement_annotation_returns_none(self):
        ann = parse(tokenize('module m { func f(x: int) type int { return x } }'))
        funcs = [n for n in _walk(ann) if hasattr(n, 'params') and n.params]
        assert extract(funcs[0].params[0].type_ann) is None

    def test_refinement_shape_is_parsed(self):
        ann = parse(tokenize(
            'module m { func f(x: { v: int | v > 0 }) type int { return x } }'))
        funcs = [n for n in _walk(ann) if hasattr(n, 'params') and n.params]
        ref = extract(funcs[0].params[0].type_ann)
        assert ref is not None
        assert ref.variable == 'v' and ref.base_kind == 'int'


def _walk(node, acc=None):
    if acc is None:
        acc = []
    if node is None:
        return acc
    if hasattr(node, '__dataclass_fields__'):
        acc.append(node)
    if isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, acc)
    elif hasattr(node, '__dataclass_fields__'):
        for f in node.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            _walk(getattr(node, f, None), acc)
    return acc
