"""Closures: `\\(x: T) -> body` captures its free variables by value.

Before this, `_compile_lambda_expr` emitted a bare `i32.const 0` — every lambda was
null, and calling one trapped.  A closure value is now a 2-word heap block
`[table_index, env_ptr]`; the generated function takes the environment as its first
parameter; and a call site loads the pair and `call_ref`s the table entry.

Captures are BY VALUE at creation: reassigning the captured name afterwards must not
be visible through the closure.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.compiler_wasm import compile_file_to_wasm
from svl.closures import collect_lambdas, free_variables
from svl.lexer import tokenize
from svl.parser_rd import LambdaExpr, parse
from svl.repl import run_wat
from svl.verify_gate import SVLVerificationError


def _run(src):
    rv, out = run_wat(compile_file_to_wasm(src))
    return rv


def _lam(src):
    return [n for n in collect_lambdas(parse(tokenize(src)))
            if isinstance(n, LambdaExpr)][0]


class TestClosures:
    def test_capture_and_call(self):
        src = ('module m { func main() type int '
               '{ let g = \\(y: int) -> y + 2  return g(40) } }')
        assert _run(src) == 42

    def test_two_captures(self):
        src = ('module m { func main() type int { let a = 10  let b = 20 '
               ' let g = \\(y: int) -> y + a + b  return g(12) } }')
        assert _run(src) == 42

    def test_two_parameters(self):
        src = ('module m { func main() type int '
               '{ let g = \\(a: int, b: int) -> a * b  return g(6, 7) } }')
        assert _run(src) == 42

    def test_no_capture(self):
        src = ('module m { func main() type int '
               '{ let g = \\(y: int) -> y * 2  return g(21) } }')
        assert _run(src) == 42

    def test_closure_passed_to_a_function(self):
        src = ('module m { func apply(h: fn(int) -> int, v: int) type int '
               '{ return h(v) }  func main() type int '
               '{ let g = \\(y: int) -> y + 1  return apply(g, 41) } }')
        assert _run(src) == 42

    def test_closure_returned_from_a_function(self):
        src = ('module m { func make() type fn(int) -> int '
               '{ return \\(y: int) -> y + 100 }  func main() type int '
               '{ let h = make()  return h(1) } }')
        assert _run(src) == 101

    def test_capture_is_by_value(self):
        """Reassigning the captured name after creation must not be visible."""
        src = ('module m { func main() type int { let a = 5 '
               ' let g = \\(y: int) -> y + a  a = 99  return g(1) } }')
        assert _run(src) == 6

    def test_nested_lambda_captures_from_the_enclosing_lambda(self):
        src = ('module m { func main() type int { let g = \\(y: int) -> '
               '\\(z: int) -> z + y  let h = g(40)  return h(2) } }')
        assert _run(src) == 42

    def test_two_closures_do_not_share_an_environment(self):
        src = ('module m { func main() type int '
               '{ let a = \\(y: int) -> y + 1  let b = \\(y: int) -> y + 2 '
               ' return a(40) + b(39) } }')
        assert _run(src) == 82


class TestCaptureAnalysis:
    def test_free_variables_sorted(self):
        lam = _lam('module m { func f() type int '
                   '{ let g = \\(y: int) -> y + b + a  return 0 } }')
        assert free_variables(lam) == ['a', 'b']

    def test_parameters_are_not_free(self):
        lam = _lam('module m { func f() type int '
                   '{ let g = \\(y: int) -> y + 1  return 0 } }')
        assert free_variables(lam) == []

    def test_excluded_names_are_not_captured(self):
        lam = _lam('module m { func f() type int '
                   '{ let g = \\(y: int) -> y + 1  return 0 } }')
        assert free_variables(lam, exclude={'y'}) == []

    def test_collect_lambdas_finds_nested_ones(self):
        ast = parse(tokenize('module m { func f() type int '
                             '{ let g = \\(y: int) -> \\(z: int) -> z + y '
                             ' return 0 } }'))
        assert len(collect_lambdas(ast)) == 2


class TestNoFalsePositives:
    def test_a_program_without_lambdas_is_unaffected(self):
        src = 'module m { func main() type int { return 42 } }'
        assert _run(src) == 42

    def test_named_functions_still_call_directly(self):
        src = ('module m { func add(a: int, b: int) type int { return a + b } '
               ' func main() type int { return add(40, 2) } }')
        assert _run(src) == 42

    def test_an_unknown_callee_is_still_refused(self):
        src = 'module m { func main() type int { return nope(1) } }'
        with pytest.raises(SVLVerificationError):
            compile_file_to_wasm(src)
