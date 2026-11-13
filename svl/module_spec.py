# svl/module_spec.py
# Whole-program specification: module-scoped `requires`/`ensures` over the entry point.
#
# Per-function contracts describe what each function guarantees.  A module-level clause
# describes what the PROGRAM guarantees: it applies to the module's entry point (the
# function exported as `<module>_main`), so it covers the whole program's observable
# result rather than one function's.
#
#   module m
#     requires <expr>      // the caller's obligation to the program
#     ensures  <expr>      // what the program guarantees about its result
#   { func main() type int { ... } }
#
# The clauses are merged with the entry point's own (`A && B`) and discharged by the same
# contract prover, so a module spec is proved, not tested.  A module with a spec but no
# `main` is a problem — there is no entry point for the spec to describe.

from dataclasses import replace
from typing import Any, List, Optional

from svl.parser_rd import FuncDecl, BinaryExpr, NodeType


def entry_point(module: Any) -> Optional[FuncDecl]:
    """The module's entry function — the one exported as `<module>_main`."""
    for stmt in getattr(module.body, 'statements', []) or []:
        if isinstance(stmt, FuncDecl) and stmt.name == 'main':
            return stmt
    return None


def _and(left: Any, right: Any) -> Any:
    """Conjunction of two clause expressions."""
    if left is None:
        return right
    if right is None:
        return left
    return BinaryExpr(type=NodeType.BINARY_EXPR, line=0, column=0, offset=0,
                      left=left, operator='&&', right=right)


def combined_entry_point(module: Any, func: FuncDecl) -> FuncDecl:
    """The entry point with the module's clauses merged into its own contract."""
    requires = _and(func.requires, module.spec_requires)
    ensures = _and(func.ensures, module.spec_ensures)
    return replace(func, requires=requires, ensures=ensures)


def check_module_spec(ast: Any) -> List[str]:
    """Discharge every module-level specification.  Returns a list of problems."""
    from svl.contract_prover import prove_ensures, prove_requires

    problems: List[str] = []
    for module in getattr(ast, 'modules', []) or []:
        if module.spec_requires is None and module.spec_ensures is None:
            continue

        func = entry_point(module)
        if func is None:
            problems.append(
                f"module '{module.name}' declares a specification but has no entry "
                f"point 'main' — the specification describes nothing")
            continue

        combined = combined_entry_point(module, func)

        req = prove_requires(combined)
        if req.status == 'counterexample':
            problems.append(f"module '{module.name}': specification: {req.obligation}")

        ens, _sound = prove_ensures(combined)
        if ens.status == 'counterexample':
            problems.append(f"module '{module.name}': specification: {ens.obligation}")

    return problems
