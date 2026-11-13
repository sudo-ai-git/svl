# svl/refinement_types.py
# Refinement types `{ v: T | P(v) }` — introduction and elimination, discharged in Z3.
#
# Semantics implemented here:
#
#   * A refinement `{ v: T | P(v) }` is the type of `T` values satisfying `P`.
#   * **Introduction (must prove).** Every place a refined value is *produced* carries
#     an obligation:
#       - `let x: {v: int | P} = e`        → prove `P[e/v]`
#       - `f(a)` with `f(x: {v: int | P})` → prove `P[a/v]` at the call site
#       - `return e` with a refined return  → prove `P[e/v]`
#   * **Elimination (may assume).** Where a refined value is *bound*, `P` is assumed:
#       - inside a function, a refined parameter gives `P(param)` for free
#       - after a proven `let x: {v: int | P} = e`, `P(x)` holds for the rest of the scope
#
# The decidable class is QF_LIA over `int` (and `bool` predicates).  Anything the
# expression encoder declines — `/`, `%`, calls, arrays, structs, floats — is reported
# as `unverified`, never assumed and never used to discharge.  A proven counterexample
# is a hard error; a decline is silence, the same contract the interval analyser keeps.
#
# This module is an ENGINE: `svl/verify_gate.py` runs `check_refinements(ast)` on the
# compile path, and `svl/feature_registry.py` records the kind as `enforced`.

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from svl.parser_rd import (
    FuncDecl, LetStmt, ReturnStmt, IfStmt, WhileStmt, ForStmt,
    CallExpr, ExprStmt, AssignExpr, Ident, Block, TypeExpr,
)


@dataclass
class Refinement:
    """A parsed refinement: variable name, base type name, predicate AST."""
    variable: str
    base_kind: str          # 'int' or 'bool' — the modelled bases
    predicate: Any          # AST expression P(v)


@dataclass
class ObligationResult:
    status: str             # 'proven' | 'counterexample' | 'unverified'
    detail: str = ""


def extract(ann: Any) -> Optional[Refinement]:
    """Pull a refinement out of a type annotation, or None if it is not one.

    Returns None for a refinement whose base type is not modelled (`float`, structs,
    arrays) — the checker then declines rather than pretending the predicate is checked.
    """
    if getattr(ann, 'kind', None) != 'refinement':
        return None
    value = ann.value
    if not isinstance(value, dict):
        return None
    var = value.get('variable')
    base = value.get('base_type')
    pred = value.get('predicate')
    if not isinstance(var, str) or pred is None or base is None:
        return None
    base_kind = _base_kind(base)
    if base_kind is None:
        return None
    return Refinement(variable=var, base_kind=base_kind, predicate=pred)


def _base_kind(base_ann: Any) -> Optional[str]:
    if getattr(base_ann, 'kind', None) == 'prim' and base_ann.value in ('int', 'bool'):
        return base_ann.value
    return None


def _iter_nodes(node, want_types, acc=None):
    if acc is None:
        acc = []
    if node is None:
        return acc
    if isinstance(node, want_types):
        acc.append(node)
    if isinstance(node, (list, tuple)):
        for item in node:
            _iter_nodes(item, want_types, acc)
    elif hasattr(node, '__dataclass_fields__'):
        for f in node.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            _iter_nodes(getattr(node, f, None), want_types, acc)
    return acc


def _instantiate(ref: Refinement, replacement, z3_mod, env: Dict[str, Any]):
    """`P[replacement / v]` as a z3 term, or None if the predicate is not modellable.

    `contract_prover._expr_to_z3` already declines `/`, `%`, calls and non-integer
    literals, so an unmodelled predicate comes back as None and the caller declines.
    """
    from svl.contract_prover import _expr_to_z3
    local = dict(env)
    local[ref.variable] = replacement
    return _expr_to_z3(ref.predicate, z3_mod, local)


def _prove(predicate_term, assumptions: List[Any], z3_mod) -> ObligationResult:
    """Refute `assumptions ==> predicate`.  `unsat` proves it."""
    if predicate_term is None:
        return ObligationResult('unverified', 'predicate not modelled')
    solver = z3_mod.Solver()
    for a in assumptions:
        solver.add(a)
    solver.add(z3_mod.Not(predicate_term))
    res = solver.check()
    if res == z3_mod.unsat:
        return ObligationResult('proven')
    if res == z3_mod.sat:
        model = solver.model()
        vals = []
        for d in model.decls():
            vals.append(f"{d.name()}={model[d]}")
        # An empty model means the predicate is unsatisfiable outright — there is no
        # assignment to name, which is the strongest possible refutation.
        return ObligationResult(
            'counterexample',
            ", ".join(vals) if vals else "no assignment satisfies it")
    return ObligationResult('unverified', 'solver returned unknown')


class RefinementChecker:
    """Walks a program and discharges every refinement obligation it can model."""

    def __init__(self, ast: Any):
        self.ast = ast
        self.functions: Dict[str, FuncDecl] = {}
        self.problems: List[str] = []

    def run(self) -> List[str]:
        for func in _iter_nodes(self.ast, (FuncDecl,)):
            self.functions.setdefault(func.name, func)
        for func in self.functions.values():
            self._check_function(func)
        return self.problems

    # -- functions ------------------------------------------------------------

    def _check_function(self, func: FuncDecl) -> None:
        try:
            import z3 as z3_mod
        except ImportError:
            return                                     # z3 absent: decline entirely

        env: Dict[str, Any] = {}
        assumptions: List[Any] = []
        for p in func.params:
            term = z3_mod.Int(p.name)
            env[p.name] = term
            ref = extract(p.type_ann) if p.type_ann is not None else None
            if ref is None:
                continue
            inst = _instantiate(ref, term, z3_mod, env)
            if inst is not None:
                assumptions.append(inst)               # elimination

        ret_ref = extract(func.return_type) if func.return_type is not None else None
        self._walk_block(func.body, env, assumptions, ret_ref, func.name, z3_mod)

    # -- statements -----------------------------------------------------------

    def _walk_block(self, block, env, assumptions, ret_ref, func_name, z3_mod) -> None:
        env = dict(env)
        assumptions = list(assumptions)
        for stmt in getattr(block, 'statements', []) or []:
            if isinstance(stmt, LetStmt):
                self._check_let(stmt, env, assumptions, z3_mod)

            elif isinstance(stmt, ReturnStmt):
                self._check_return(stmt, env, assumptions, ret_ref, func_name, z3_mod)
                self._check_calls(stmt.value, env, assumptions, z3_mod)

            elif isinstance(stmt, IfStmt):
                self._check_calls(stmt.condition, env, assumptions, z3_mod)
                self._walk_block(stmt.then_branch, env, assumptions, ret_ref,
                                 func_name, z3_mod)
                if stmt.else_branch is not None:
                    self._walk_block(stmt.else_branch, env, assumptions, ret_ref,
                                     func_name, z3_mod)

            elif isinstance(stmt, (WhileStmt, ForStmt)):
                self._check_calls(getattr(stmt, 'condition', None), env, assumptions, z3_mod)
                # A loop may run 0..n times, so the values its body produces are not
                # straight-line.  Taint what it can assign and keep checking the rest.
                modified = _assigned_names(stmt)
                for name in modified:
                    env.pop(name, None)
                self._walk_block(stmt.body, env, assumptions, ret_ref, func_name, z3_mod)

            elif isinstance(stmt, ExprStmt):
                self._check_calls(stmt.expression, env, assumptions, z3_mod)

            elif hasattr(stmt, 'expression'):
                self._check_calls(stmt.expression, env, assumptions, z3_mod)

    def _check_let(self, stmt, env, assumptions, z3_mod) -> None:
        ref = extract(stmt.type_ann) if stmt.type_ann is not None else None
        val_term = _expr_to_z3_safe(stmt.value, z3_mod, env)
        # Calls in the value are checked in the environment BEFORE the binding exists.
        self._check_calls(stmt.value, env, assumptions, z3_mod)

        if ref is not None:
            if val_term is None:
                return                                 # value not modelled: decline
            inst = _instantiate(ref, val_term, z3_mod, env)
            if inst is None:
                return                                 # predicate not modelled: decline
            res = _prove(inst, assumptions, z3_mod)
            if res.status == 'counterexample':
                self.problems.append(
                    f"line {getattr(stmt, 'line', '?')}: refinement on '{stmt.name}' is "
                    f"violated — {ref.variable} = {val_term} does not satisfy the "
                    f"predicate ({res.detail})"
                )
                return
            if res.status == 'proven':
                assumptions.append(inst)               # elimination
                env[stmt.name] = val_term
            # unverified: silence
            return

        if val_term is not None:
            env[stmt.name] = val_term

    def _check_return(self, stmt, env, assumptions, ret_ref, func_name, z3_mod) -> None:
        if ret_ref is None or stmt.value is None:
            return
        val_term = _expr_to_z3_safe(stmt.value, z3_mod, env)
        if val_term is None:
            return
        inst = _instantiate(ret_ref, val_term, z3_mod, env)
        if inst is None:
            return
        res = _prove(inst, assumptions, z3_mod)
        if res.status == 'counterexample':
            self.problems.append(
                f"line {getattr(stmt, 'line', '?')}: return does not satisfy the "
                f"refined return type ({res.detail})"
            )

    # -- calls ----------------------------------------------------------------

    def _check_calls(self, expr, env, assumptions, z3_mod) -> None:
        """Find every call in an expression and discharge its refined parameters."""
        if expr is None:
            return
        if isinstance(expr, CallExpr):
            func = self.functions.get(expr.callee)
            if func is not None:
                for param, arg in zip(func.params, expr.arguments):
                    ref = extract(param.type_ann) if param.type_ann is not None else None
                    if ref is None:
                        continue
                    arg_term = _expr_to_z3_safe(arg, z3_mod, env)
                    if arg_term is None:
                        continue
                    inst = _instantiate(ref, arg_term, z3_mod, env)
                    if inst is None:
                        continue
                    res = _prove(inst, assumptions, z3_mod)
                    if res.status == 'counterexample':
                        self.problems.append(
                            f"line {getattr(expr, 'line', '?')}: call to "
                            f"'{expr.callee}' violates the refinement on parameter "
                            f"'{param.name}' ({res.detail})"
                        )
            for arg in expr.arguments:
                self._check_calls(arg, env, assumptions, z3_mod)
            return
        if isinstance(expr, (list, tuple)):
            for item in expr:
                self._check_calls(item, env, assumptions, z3_mod)
            return
        if hasattr(expr, '__dataclass_fields__'):
            for f in expr.__dataclass_fields__:
                if f in ('line', 'column', 'offset', 'type'):
                    continue
                self._check_calls(getattr(expr, f, None), env, assumptions, z3_mod)


def _expr_to_z3_safe(expr, z3_mod, env):
    from svl.contract_prover import _expr_to_z3
    return _expr_to_z3(expr, z3_mod, env)


def _assigned_names(stmt) -> set:
    out = set()

    def visit(node):
        if node is None:
            return
        if isinstance(node, ExprStmt) and isinstance(node.expression, AssignExpr):
            if isinstance(node.expression.target, Ident):
                out.add(node.expression.target.name)
            return
        if isinstance(node, AssignExpr) and isinstance(node.target, Ident):
            out.add(node.target.name)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                visit(item)
            return
        if hasattr(node, '__dataclass_fields__'):
            for f in node.__dataclass_fields__:
                if f in ('line', 'column', 'offset', 'type'):
                    continue
                visit(getattr(node, f, None))

    visit(stmt)
    return out


def check_refinements(ast: Any) -> List[str]:
    """Entry point for the compile gate: every refinement violation in the program."""
    return RefinementChecker(ast).run()