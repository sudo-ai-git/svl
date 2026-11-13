# svl/vec_bounds.py
# `vec<T, n>` — dependent array bounds, checked against the initializer.
#
# `vec<int, 3>` asserts that the bound value has exactly 3 elements.  The parser has
# accepted the syntax all along; nothing checked it, so `vec<int, 3> = [1,2]` compiled
# and silently behaved as a 2-element array.  This module checks the bound when BOTH
# sides are literal:
#
#   * the declared size must be an integer literal;
#   * the initializer's length must be determinable — an array literal, or `zeros(k)`
#     with an integer literal k.
#
# If either side is not literal the check is SILENCE, never a guess: a wrong guess would
# reject a correct program.  The kind is registered as `enforced` because a bound that
# can be checked IS checked, and one that cannot is not claimed.

from typing import Any, List, Optional

from svl.parser_rd import (
    ArrayLit, CallExpr, ConstDecl, LetStmt, Literal, VarDecl,
)


def _literal_int(expr: Any) -> Optional[int]:
    """The value of an integer literal, or None."""
    if isinstance(expr, Literal) and isinstance(expr.value, int) \
            and not isinstance(expr.value, bool):
        return expr.value
    return None


def initializer_length(expr: Any) -> Optional[int]:
    """How many elements an initializer produces, or None when undeterminable.

    Known: an array literal, and `zeros(k)` with a literal k.  Anything else (a bare
    name, `len(x)`, a call) is undeterminable and therefore not checked.
    """
    if isinstance(expr, ArrayLit):
        return len(expr.elements)
    if isinstance(expr, CallExpr) and expr.callee == 'zeros' and len(expr.arguments) == 1:
        return _literal_int(expr.arguments[0])
    return None


def _bound_statements(node, acc=None) -> List[Any]:
    if acc is None:
        acc = []
    if node is None:
        return acc
    if isinstance(node, (LetStmt, ConstDecl, VarDecl)):
        acc.append(node)
    if isinstance(node, (list, tuple)):
        for item in node:
            _bound_statements(item, acc)
    elif hasattr(node, '__dataclass_fields__'):
        for f in node.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            _bound_statements(getattr(node, f, None), acc)
    return acc


def check_vec_bounds(ast: Any) -> List[str]:
    """Every checkable `vec<T, n>` bound must match its initializer's length."""
    problems: List[str] = []
    for stmt in _bound_statements(ast):
        ann = getattr(stmt, 'type_ann', None)
        if ann is None or getattr(ann, 'kind', None) != 'vec':
            continue
        value = ann.value
        if not isinstance(value, dict):
            continue
        _check_one(value, getattr(stmt, 'value', None), stmt, problems)
    return problems


def _check_one(ann_value: dict, initializer, stmt, problems: List[str]) -> None:
    """Check one `vec` annotation, recursing into a nested element bound."""
    name = getattr(stmt, 'name', '?')
    line = getattr(stmt, 'line', '?')

    expected = _literal_int(ann_value.get('size'))
    if expected is not None:
        actual = initializer_length(initializer)
        if actual is not None and actual != expected:
            problems.append(
                f"line {line}: '{name}' is declared vec<{expected}> but the "
                f"initializer has {actual} element(s)")
            return

    element = ann_value.get('element_type')
    if element is None or getattr(element, 'kind', None) != 'vec':
        return
    inner = element.value
    if not isinstance(inner, dict):
        return
    inner_expected = _literal_int(inner.get('size'))
    if inner_expected is None or not isinstance(initializer, ArrayLit):
        return
    for element_expr in initializer.elements:
        actual = initializer_length(element_expr)
        if actual is not None and actual != inner_expected:
            problems.append(
                f"line {getattr(element_expr, 'line', line)}: '{name}' is declared "
                f"vec<vec<{inner_expected}>> but an element has {actual} element(s)")
