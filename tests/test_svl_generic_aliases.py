"""Generic type aliases — `type Name<p1..pn> = target`, transparent on use.

Before this, `_check_type_alias` was `pass`: an alias was accepted as syntax and then
treated as an opaque generic, so `type Box<a> = [a]` made `Box<int>` an opaque `Box`
rather than an array of int.  Aliases are now recorded in the type environment and
substituted into their target on every use.

The substitution also exposed two latent defects: `array` and `tuple` annotations
referenced `ann.args`, a field `TypeExpr` does not have, so BOTH had never type-checked
(`func f(a: [int])` raised AttributeError).  `[T]` now lowers to `List<T>` — the same
type an array literal synthesizes — so `let b: [int] = [40, 2]` unifies.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from svl.compiler_wasm import compile_file_to_wasm
from svl.lexer import tokenize
from svl.parser_rd import parse
from svl.repl import run_wat
from svl.type_inference import TypeChecker, substitute_type_expr
from svl.verify_gate import SVLVerificationError


def _run(src):
    rv, out = run_wat(compile_file_to_wasm(src))
    return rv


class TestGenericAliases:
    def test_alias_to_array(self):
        src = ('module m { type Box<a> = [a]  func main() type int '
               '{ let b: Box<int> = [40, 2]  return len(b) } }')
        assert _run(src) == 2

    def test_alias_to_struct(self):
        src = ('module m { struct P { x: int }  type Coord<a> = P '
               ' func main() type int { let c: Coord<int> = P{x: 42}  return c.x } }')
        assert _run(src) == 42

    def test_alias_parameter_is_substituted(self):
        """The parameter appears in the target, so it must be replaced."""
        src = ('module m { type Wrapper<a> = [a]  func main() type int '
               '{ let w: Wrapper<int> = [7]  return w[0] } }')
        assert _run(src) == 7

    def test_two_parameter_alias(self):
        src = ('module m { type Compose<a, b> = fn(a) -> b  func main() type int '
               '{ let f: Compose<int, int> = \\(x: int) -> x + 2  return f(40) } }')
        assert _run(src) == 42

    def test_unused_alias_is_harmless(self):
        src = 'module m { type Box<a> = [a]  func main() type int { return 7 } }'
        assert _run(src) == 7

    def test_arity_mismatch_is_still_refused(self):
        src = ('module m { type Box<a> = [a]  func main() type int '
               '{ let b: Box<int, int> = [1]  return 0 } }')
        with pytest.raises(SVLVerificationError):
            compile_file_to_wasm(src)

    def test_a_non_alias_generic_is_unaffected(self):
        src = 'module m { func main() type int { let x: Option<int> = 1  return x } }'
        assert _run(src) == 1


class TestArrayAndTupleAnnotations:
    """Both had NEVER type-checked — `TypeExpr` has no `args` field."""

    def test_array_annotation(self):
        src = ('module m { func f(a: [int]) type int { return len(a) } '
               ' func main() type int { return f([40, 2]) } }')
        assert _run(src) == 2

    def test_array_annotation_matches_a_literal(self):
        src = ('module m { func main() type int '
               '{ let b: [int] = [40, 2]  return len(b) } }')
        assert _run(src) == 2


class TestSubstitution:
    def test_bare_name_is_replaced(self):
        from svl.parser_rd import TypeExpr, NodeType
        te = TypeExpr(type=NodeType.TYPE_EXPR, line=0, column=0, offset=0,
                      kind='struct', value='a')
        arg = TypeExpr(type=NodeType.TYPE_EXPR, line=0, column=0, offset=0,
                       kind='prim', value='int')
        assert substitute_type_expr(te, {'a': arg}) is arg

    def test_nested_target_is_rebuilt(self):
        from svl.parser_rd import TypeExpr, NodeType
        inner = TypeExpr(type=NodeType.TYPE_EXPR, line=0, column=0, offset=0,
                         kind='struct', value='a')
        arr = TypeExpr(type=NodeType.TYPE_EXPR, line=0, column=0, offset=0,
                       kind='array', value=inner)
        arg = TypeExpr(type=NodeType.TYPE_EXPR, line=0, column=0, offset=0,
                       kind='prim', value='int')
        out = substitute_type_expr(arr, {'a': arg})
        assert out.kind == 'array' and out.value is arg

    def test_unrelated_names_are_untouched(self):
        from svl.parser_rd import TypeExpr, NodeType
        te = TypeExpr(type=NodeType.TYPE_EXPR, line=0, column=0, offset=0,
                      kind='prim', value='int')
        assert substitute_type_expr(te, {'a': te}) is te


class TestNoFalsePositives:
    def test_a_program_without_aliases_is_unaffected(self):
        src = 'module m { func main() type int { return 42 } }'
        assert _run(src) == 42

    def test_a_plain_array_still_works(self):
        src = ('module m { func main() type int { let a = [40, 2]  return len(a) } }')
        assert _run(src) == 2
