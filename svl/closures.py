# svl/closures.py
# Closure analysis: lambda discovery, free variables, capture layout.
#
# A closure value is a 2-word heap block `[table_index, env_ptr]`:
#   * `table_index` indexes a `funcref` table holding the closure's generated function;
#   * `env_ptr` points at a block of captured values.
#
# Captures are BY VALUE at creation.  SVL has no mutable captured state, so by-value is
# the honest semantics: a later assignment to the captured name must not be visible
# through the closure (and is not).
#
# The generated function takes the environment pointer as its FIRST parameter, so every
# closure signature is `<env: i32> <params...> -> <ret>`.  Call sites load the two words
# and `call_ref` the table entry.

from typing import Any, Iterator, List, Optional

from svl.parser_rd import LambdaExpr, Ident


def children(node) -> Iterator[Any]:
    """Child nodes of an AST node, skipping position fields."""
    if isinstance(node, (list, tuple)):
        for item in node:
            yield item
        return
    if hasattr(node, '__dataclass_fields__'):
        for f in node.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            yield getattr(node, f, None)


def walk(node) -> Iterator[Any]:
    """Every AST node in the tree, pre-order."""
    if node is None:
        return
    if hasattr(node, '__dataclass_fields__'):
        yield node
    for child in children(node):
        if hasattr(child, '__dataclass_fields__') or isinstance(child, (list, tuple)):
            yield from walk(child)


def collect_lambdas(node, acc: Optional[List[LambdaExpr]] = None) -> List[LambdaExpr]:
    """Every LambdaExpr in the tree, in deterministic pre-order."""
    if acc is None:
        acc = []
    for n in walk(node):
        if isinstance(n, LambdaExpr):
            acc.append(n)
    return acc


def free_variables(lam: LambdaExpr, exclude: Optional[set] = None) -> List[str]:
    """The lambda's free variables, sorted (deterministic capture order).

    `exclude` removes names that are not local values — globals, functions and struct
    names.  Capturing a global would freeze a value the program expects to be live, so
    those are left to resolve as globals inside the closure body.
    """
    exclude = exclude or set()
    bound = {p.name for p in lam.params}
    found: List[str] = []

    def visit(node, bound):
        if node is None:
            return
        if isinstance(node, Ident):
            if (node.name not in bound and node.name not in exclude
                    and node.name not in found):
                found.append(node.name)
            return
        if isinstance(node, LambdaExpr):
            # A nested lambda: its own params are bound, and its free variables become
            # ours (it captures from our scope).
            inner = bound | {p.name for p in node.params}
            visit(node.body, inner)
            return
        for child in children(node):
            if hasattr(child, '__dataclass_fields__') or isinstance(child, (list, tuple)):
                visit(child, bound)

    visit(lam.body, bound)
    return sorted(found)


def signature_string(param_types: List[str], ret_type: Optional[str]) -> str:
    """A canonical closure signature, e.g. `(i32 i32) -> i32`.

    The first parameter is always the environment pointer.
    """
    params = ' '.join(param_types)
    if ret_type:
        return f'({params}) -> {ret_type}'
    return f'({params}) -> ()'
