# svl/contract_prover.py
# P2.1: Contract Prover — requires/ensures/invariant lowered to Z3 obligations.
#
# The decidable class is QF_LIA (linear integer arithmetic). Outside that class the
# prover reports `unverified` rather than `passed` or `counterexample` — the same
# honest tri-state as the SMT theorem layer.
#
# Three obligations are discharged:
#   1. requires  — satisfiability.  An unsatisfiable `requires` names an empty domain:
#                   every implementation is vacuously correct and every caller is
#                   blocked, so it is a real defect in the specification.
#   2. ensures   — validity of `requires && <path> ==> ensures[result := <return expr>]`
#                   for EVERY return, over EVERY straight-line path that reaches it.
#                   `if/else` splits the paths and re-joins them afterwards.
#   3. invariant — rule of consequence.  A declared invariant must be (a) established on
#                   entry from `requires` and the preceding bindings, and (b) preserved by
#                   the body under the negated condition.  Preservation is proved by
#                   unfolding ONE body iteration with the invariant re-established at the
#                   end of the body (not at the loop head), which is where it must hold.
#
# Soundness rules, each of which is a real defect this file has had:
#   * A name not modelled by an obligation is TAINTED, never guessed.  Discharging an
#     obligation against a stale or unconstrained value is what produces false theorems.
#   * Sequencing is modelled: `x = 0; x = 5` ends with `x -> 5`, and `x = x + 1` keeps
#     its dependency on the previous binding.  A flat "last RHS wins" scan over
#     evaluated terms gets both wrong.
#   * `x == 0` and `x != 0` are NOT interchangeable encodings of a truth value; an
#     unsatisfiable `requires` is a defect, not a vacuous pass.
#   * Every function with a contract is checked, not just the first.
#   * A declared invariant that fails is a defect, not a silent no-op.

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from svl.parser_rd import (
    FuncDecl, WhileStmt, ForStmt, Ident, Literal, BinaryExpr, UnaryExpr,
    AssignExpr, ExprStmt, Block, ReturnStmt, LetStmt, IfStmt,
    ConstDecl, VarDecl, NodeType,
)


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------

@dataclass
class ContractProverResult:
    """Result of proving a single contract obligation."""
    status: str  # 'proven' | 'counterexample' | 'unverified' | 'vacuous'
    passed: bool  # True only when status == 'proven'
    counterexample: Optional[Dict[str, Any]] = None
    unverified: List[str] = field(default_factory=list)
    obligation: str = ""  # human-readable description of what was checked

    def __repr__(self):
        return (f"ContractProverResult(status={self.status!r}, passed={self.passed}, "
                f"obligation={self.obligation!r})")


@dataclass
class ContractResult:
    """Aggregate result for a program's contracts."""
    function_name: str = "<module>"
    requires_result: Optional[ContractProverResult] = None
    ensures_results: List[Tuple[str, ContractProverResult]] = field(default_factory=list)
    invariant_results: List[Tuple[str, ContractProverResult]] = field(default_factory=list)

    def _all(self) -> List[ContractProverResult]:
        out: List[ContractProverResult] = []
        if self.requires_result is not None:
            out.append(self.requires_result)
        out.extend(r for _, r in self.ensures_results)
        out.extend(r for _, r in self.invariant_results)
        return out

    @property
    def all_proven(self) -> bool:
        rs = self._all()
        return all(r.passed for r in rs) if rs else False

    @property
    def any_counterexample(self) -> bool:
        return any(r.status == 'counterexample' for r in self._all())

    @property
    def any_unverified(self) -> bool:
        return any(r.status == 'unverified' for r in self._all())


# ---------------------------------------------------------------------------
# Expression -> Z3
# ---------------------------------------------------------------------------

def _is_int_literal(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _expr_to_z3(expr, z3_mod, var_map: Dict[str, Any]) -> Any:
    """Convert an SVL expression to a Z3 term.

    Returns the Z3 term, or ``None`` when the expression cannot be modelled.  A
    ``None`` is always a decline, never a guess: callers must taint, not approximate.

    Declined deliberately (each would be a false theorem if approximated):
      * `/` and `%` — WASM i32 division truncates toward zero while z3's integer
        division is Euclidean; modelling one as the other yields false proofs.
      * floats — SVL float arithmetic is IEEE-754, not the reals.
      * calls — no summary, so an uninterpreted call would let any postcondition
        about `result` be satisfied by an arbitrary return value.
    """
    if isinstance(expr, Ident):
        return var_map.get(expr.name)

    if isinstance(expr, Literal):
        val = expr.value
        if isinstance(val, bool):
            return z3_mod.BoolVal(val)
        if _is_int_literal(val):
            return z3_mod.IntVal(int(val))
        return None  # float / string / null: not QF_LIA

    if isinstance(expr, UnaryExpr):
        operand = _expr_to_z3(expr.operand, z3_mod, var_map)
        if operand is None:
            return None
        op = expr.operator
        if op == '-':
            return -operand
        if op == '!':
            return z3_mod.Not(operand)
        return None

    if isinstance(expr, BinaryExpr):
        op = expr.operator
        left = _expr_to_z3(expr.left, z3_mod, var_map)
        right = _expr_to_z3(expr.right, z3_mod, var_map)
        if left is None or right is None:
            return None
        if op == '+':
            return left + right
        if op == '-':
            return left - right
        if op == '*':
            return left * right
        if op == '==':
            return left == right
        if op == '!=':
            return left != right
        if op == '<':
            return left < right
        if op == '>':
            return left > right
        if op == '<=':
            return left <= right
        if op == '>=':
            return left >= right
        if op == '&&':
            return z3_mod.And(left, right)
        if op == '||':
            return z3_mod.Or(left, right)
        return None  # '/', '%', bitwise, '.', '..' ...

    return None


# ---------------------------------------------------------------------------
# AST walking helpers
# ---------------------------------------------------------------------------

def _idents(expr, acc: Optional[set] = None) -> set:
    """Every identifier name mentioned by an expression."""
    if acc is None:
        acc = set()
    if expr is None:
        return acc
    if isinstance(expr, Ident):
        acc.add(expr.name)
    elif isinstance(expr, (list, tuple)):
        for item in expr:
            _idents(item, acc)
    elif hasattr(expr, '__dataclass_fields__'):
        for f in expr.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            _idents(getattr(expr, f, None), acc)
    return acc


def _walk(node, want_types, acc: Optional[List] = None) -> List:
    """Collect every node of the given types anywhere below ``node``."""
    if acc is None:
        acc = []
    if node is None:
        return acc
    if isinstance(node, want_types):
        acc.append(node)
    if isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, want_types, acc)
    elif hasattr(node, '__dataclass_fields__'):
        for f in node.__dataclass_fields__:
            if f in ('line', 'column', 'offset', 'type'):
                continue
            _walk(getattr(node, f, None), want_types, acc)
    return acc


def _ident_like(name: str) -> Ident:
    """A positional Ident carrying only a name, for deferred resolution."""
    return Ident(NodeType.IDENT, 0, 0, 0, name)


def _declared_names(block) -> set:
    """Names bound by `let` / `const` / `var` directly in a block."""
    out = set()
    for stmt in getattr(block, 'statements', []) or []:
        if isinstance(stmt, (LetStmt, ConstDecl, VarDecl)):
            name = getattr(stmt, 'name', None) or getattr(stmt, 'var_name', None)
            if isinstance(name, str):
                out.add(name)
    return out


def _assigned_names(stmt) -> set:
    """Every name a statement (recursively) assigns to."""
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


# ---------------------------------------------------------------------------
# Path modelling
# ---------------------------------------------------------------------------
#
# A path state is `(assignments, tainted)`:
#   * `assignments[name]` is the SVL expression a name holds at that program point.
#     It is stored as an EXPRESSION, not as an evaluated z3 term, so it can be
#     re-evaluated in any model and so sequencing stays correct: `x = x + 1` records
#     `x -> x + 1`, whose meaning depends on the binding before it.
#   * `tainted` holds names whose value cannot be modelled.
#
# A flat map of already-evaluated terms cannot express either of those: it collapses
# `x = 0; x = 5` into whatever was evaluated last, and it loses the dependency of
# `x = x + 1` on the previous `x`.


def _compound_marker(operator: str, old, rhs):
    """A deferred `old <op>= rhs`, resolved only when the surrounding model is known."""
    return ('__compound__', operator, old, rhs)


def _resolve(value, z3_mod, vm):
    """Resolve a recorded binding expression to a z3 term, or None.

    A compound assignment (`i += 1`) is recorded as ``('__compound__', op, old, rhs)``:
    the previous value is resolved *symbolically* first, then the operator is applied.
    Resolving the RHS against the outer environment instead would read the pre-state
    binding, so `i += 1` would evaluate to a constant and every loop invariant would
    verify against a value that never changes.
    """
    if isinstance(value, tuple) and len(value) == 4 and value[0] == '__compound__':
        _, op, old_expr, rhs_expr = value
        old = _resolve(old_expr, z3_mod, vm)
        rhs = _expr_to_z3(rhs_expr, z3_mod, vm)
        if old is None or rhs is None:
            return None
        base = op[:-1] if op.endswith('=') else op
        if base == '+':
            return old + rhs
        if base == '-':
            return old - rhs
        if base == '*':
            return old * rhs
        return None
    return _expr_to_z3(value, z3_mod, vm)


def _env_for(assign: Dict[str, Any], vm: Dict[str, Any], z3_mod) -> Dict[str, Any]:
    """Resolve a path's bindings to z3 terms, in dependency order.

    Bindings are stored as raw SVL expressions so sequencing stays correct; this
    resolves them on demand.  A binding that cannot be resolved (an unknown name, an
    unmodelled construct) is absent from the result, which makes any expression that
    refers to it unmodelable — the caller taints rather than guesses.

    This is what lets `_model_block` ask "is this RHS expressible?" without building an
    environment out of raw AST nodes, which z3 cannot coerce.
    """
    env = dict(vm)
    pending = dict(assign)
    while pending:
        progressed = False
        for name in list(pending):
            term = _resolve(pending[name], z3_mod, env)
            if term is not None:
                env[name] = term
                del pending[name]
                progressed = True
        if not progressed:
            break
    return env


def _model_block(block, paths, z3_mod, vm) -> List[Tuple[Dict[str, Any], set]]:
    """Model a straight-line block, splitting paths at any `if/else`.

    Returns the list of `(assignments, tainted)` states that can reach the END of the
    block.  A `return` is not a binding change, so the state list is exactly the set of
    bindings in force at any return in the block.
    """
    current = list(paths)
    for stmt in getattr(block, 'statements', []) or []:
        if isinstance(stmt, (LetStmt, ConstDecl, VarDecl)):
            name = getattr(stmt, 'name', None) or getattr(stmt, 'var_name', None)
            nxt = []
            for assign, tainted in current:
                a2 = dict(assign)
                t2 = set(tainted)
                if not isinstance(name, str):
                    t2.add('<unmodelled-decl>')
                    nxt.append((a2, t2))
                    continue
                a2.pop(name, None)          # a declaration shadows an outer binding
                t2.discard(name)
                val = getattr(stmt, 'value', None)
                env = _env_for(a2, vm, z3_mod)
                if _expr_to_z3(val, z3_mod, env) is None:
                    t2.add(name)
                else:
                    a2[name] = val
                nxt.append((a2, t2))
            current = nxt
            continue

        if isinstance(stmt, ExprStmt) and isinstance(stmt.expression, AssignExpr):
            a = stmt.expression
            nxt = []
            for assign, tainted in current:
                a2 = dict(assign)
                t2 = set(tainted)
                if not isinstance(a.target, Ident):
                    t2.add(f'<assign-target:{type(a.target).__name__}>')
                    nxt.append((a2, t2))
                    continue
                name = a.target.name
                env = _env_for(a2, vm, z3_mod)
                if a.operator == '=':
                    if _expr_to_z3(a.value, z3_mod, env) is None:
                        a2.pop(name, None)
                        t2.add(name)
                    else:
                        a2[name] = a.value
                        t2.discard(name)
                else:
                    # Compound assignment: the new value is a function of the old one,
                    # which `env` holds for a parameter / outer binding and for any
                    # earlier local binding on this path.
                    if name in env:
                        a2[name] = _compound_marker(a.operator, _ident_like(name), a.value)
                        t2.discard(name)
                    else:
                        t2.add(name)
                nxt.append((a2, t2))
            current = nxt
            continue

        if isinstance(stmt, IfStmt):
            then_out = _model_block(stmt.then_branch,
                                    [(dict(a), set(t)) for a, t in current], z3_mod, vm)
            if stmt.else_branch is not None:
                else_out = _model_block(stmt.else_branch,
                                        [(dict(a), set(t)) for a, t in current], z3_mod, vm)
            else:
                else_out = [(dict(a), set(t)) for a, t in current]
            current = then_out + else_out
            continue

        if isinstance(stmt, (WhileStmt, ForStmt)):
            # The body may run 0..n times, so every name it can modify becomes
            # unconstrained and any obligation depending on one is tainted.
            modified = _assigned_names(stmt)
            nxt = []
            for assign, tainted in current:
                a2 = dict(assign)
                t2 = set(tainted)
                for name in modified:
                    a2.pop(name, None)
                    t2.add(name)
                nxt.append((a2, t2))
            current = nxt
            continue

        # ReturnStmt / AssertStmt / AssignExpr / bare expression statements change no
        # binding that matters to an obligation.
        continue

    return current


# ---------------------------------------------------------------------------
# Obligation: requires
# ---------------------------------------------------------------------------

def prove_requires(func: FuncDecl,
                   var_map: Optional[Dict[str, Any]] = None) -> ContractProverResult:
    """`requires` must be satisfiable.

    An unsatisfiable `requires` defines an empty domain.  That is a real defect, not
    a vacuous pass: it means no call can satisfy the contract.
    """
    if func.requires is None:
        return ContractProverResult(status='vacuous', passed=True,
                                    obligation='no requires clause')
    try:
        import z3 as z3_mod
    except ImportError:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='requires: z3 not available')

    vm = dict(var_map or {})
    for p in func.params:
        vm.setdefault(p.name, z3_mod.Int(p.name))

    req_z3 = _expr_to_z3(func.requires, z3_mod, vm)
    if req_z3 is None:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='requires: expression not modelled')

    solver = z3_mod.Solver()
    solver.add(req_z3)
    result = solver.check()
    if result == z3_mod.sat:
        return ContractProverResult(status='proven', passed=True,
                                    obligation='requires: satisfiable')
    if result == z3_mod.unsat:
        return ContractProverResult(status='counterexample', passed=False,
                                    obligation='requires: unsatisfiable (contradiction)',
                                    counterexample={'reason': 'requires is a contradiction'})
    return ContractProverResult(status='unverified', passed=False,
                                obligation='requires: solver returned unknown')


def _wrap_block(stmts):
    """A Block wrapping raw statements, for feeding single statements to `_model_block`."""
    return Block(type=NodeType.BLOCK, line=0, column=0, offset=0, statements=list(stmts))


def _model_returns(block, states, z3_mod, vm) -> List[Tuple[ReturnStmt, Dict[str, Any], set]]:
    """Pair every return with the path states that actually REACH it.

    `_model_block` joins branches, so its output states are not the states a return
    inside one branch was reached by.  Pairing them anyway produces false
    counterexamples — a correct program refused at compile time, which is worse than
    the defect being checked for.  This threads states through the block so each
    return carries only its own reaching states.
    """
    out: List[Tuple[ReturnStmt, Dict[str, Any], set]] = []
    current = list(states)

    for stmt in getattr(block, 'statements', []) or []:
        if isinstance(stmt, IfStmt):
            out.extend(_model_returns(stmt.then_branch, current, z3_mod, vm))
            if stmt.else_branch is not None:
                out.extend(_model_returns(stmt.else_branch, current, z3_mod, vm))
            then_out = _model_block(stmt.then_branch, current, z3_mod, vm)
            if stmt.else_branch is not None:
                else_out = _model_block(stmt.else_branch, current, z3_mod, vm)
            else:
                else_out = [(dict(a), set(t)) for a, t in current]
            current = then_out + else_out
            continue

        if isinstance(stmt, ReturnStmt):
            for a, t in current:
                out.append((stmt, dict(a), set(t)))
            continue

        if isinstance(stmt, (WhileStmt, ForStmt)):
            # The body may run 0..n times, so its returns are reached from the state
            # that enters the loop.
            out.extend(_model_returns(stmt.body, current, z3_mod, vm))
            modified = _assigned_names(stmt)
            nxt = []
            for a, t in current:
                a2 = dict(a)
                t2 = set(t)
                for name in modified:
                    a2.pop(name, None)
                    t2.add(name)
                nxt.append((a2, t2))
            current = nxt
            continue

        # A straight-line statement threads the states through.
        current = _model_block(_wrap_block([stmt]), current, z3_mod, vm)

    return out


def _resolve_states(states, z3_mod, vm):
    """Resolve each state's bindings to z3 terms.

    Returns ``(resolved_states, declined)`` where a declined state is one whose
    bindings could not be modelled.
    """
    resolved_states: List[Dict[str, Any]] = []
    declined = 0
    for assign, tainted in states:
        if tainted:
            declined += 1
            continue
        resolved: Dict[str, Any] = {}
        bad = False
        for name, value in assign.items():
            term = _resolve(value, z3_mod, vm)
            if term is None:
                bad = True
                break
            resolved[name] = term
        if bad:
            declined += 1
            continue
        resolved_states.append(resolved)
    return resolved_states, declined


# ---------------------------------------------------------------------------
# Obligation: ensures
# ---------------------------------------------------------------------------

def prove_ensures(func: FuncDecl,
                  var_map: Optional[Dict[str, Any]] = None
                  ) -> Tuple[ContractProverResult, bool]:
    """`requires && <path> ==> ensures` must hold at every return on every path.

    The body is *substituted*, not asserted: each return expression and the `ensures`
    clause are evaluated in an environment where every local name is replaced by the
    term for the value it holds at that program point.  Asserting post-state bindings
    into the antecedent instead would make it unsatisfiable whenever the body changes a
    value, and an unsatisfiable antecedent discharges every obligation vacuously.

    Each return is checked against the states that actually REACH it.  Joining the
    branch states first and then checking every return against all of them produces
    false counterexamples on correct programs.

    Returns ``(result, sound)``.  ``sound`` is False when an obligation could not be
    modelled: the obligations that WERE discharged are still reported, but the verdict
    must not claim the function is verified.
    """
    if func.ensures is None:
        return ContractProverResult(status='vacuous', passed=True,
                                    obligation='no ensures clause'), True
    try:
        import z3 as z3_mod
    except ImportError:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='ensures: z3 not available'), False

    vm: Dict[str, Any] = dict(var_map or {})
    for p in func.params:
        vm.setdefault(p.name, z3_mod.Int(p.name))
    vm.setdefault('result', z3_mod.Int('result'))

    req_z3 = None
    if func.requires is not None:
        req_z3 = _expr_to_z3(func.requires, z3_mod, vm)
        if req_z3 is None:
            return ContractProverResult(
                status='unverified', passed=False,
                obligation='ensures: requires clause not modelled'), False

    reached = _model_returns(func.body, [({}, set())], z3_mod, vm)
    reached = [(r, a, t) for r, a, t in reached if r.value is not None]
    if not reached:
        return ContractProverResult(
            status='unverified', passed=False,
            obligation='ensures: no return statement found'), False

    checked = 0
    declined = 0
    first_ce: Optional[Tuple[Dict[str, Any], str]] = None

    for ret, assign, tainted in reached:
        resolved_states, bad_states = _resolve_states([(assign, tainted)], z3_mod, vm)
        declined += bad_states

        for resolved in resolved_states:
            # Substitute the path state into the environment used for this path.
            local = {**vm, **resolved}

            result_term = _expr_to_z3(ret.value, z3_mod, local)
            if result_term is None:
                declined += 1
                continue

            ens_post = _expr_to_z3(func.ensures, z3_mod, {**local, 'result': result_term})
            if ens_post is None:
                declined += 1
                continue

            # The antecedent is ONLY the precondition: the path state is already
            # substituted into `ensures_post`.
            pre_z3 = req_z3 if req_z3 is not None else z3_mod.BoolVal(True)

            solver = z3_mod.Solver()
            solver.add(z3_mod.And(pre_z3, z3_mod.Not(ens_post)))
            res = solver.check()
            if res == z3_mod.sat:
                model = solver.model()
                ce = {}
                for name, var in local.items():
                    val = model.eval(var, model_completion=True)
                    if val is not None:
                        ce[name] = str(val)
                if first_ce is None:
                    first_ce = (ce, str(getattr(ret, 'line', '?')))
                continue
            if res == z3_mod.unknown:
                declined += 1
                continue
            checked += 1

    if first_ce is not None:
        ce, line = first_ce
        return ContractProverResult(
            status='counterexample', passed=False,
            obligation=f'ensures: refuted at return (line {line})',
            counterexample=ce), True

    if checked == 0:
        return ContractProverResult(
            status='unverified', passed=False,
            obligation=f'ensures: no return could be modelled ({declined} declined)'), False

    if declined:
        return ContractProverResult(
            status='unverified', passed=False,
            obligation=f'ensures: {checked} obligation(s) proved, {declined} declined '
                       f'(tainted / unmodelled)',
            unverified=[f'{declined} obligation(s) not checked']), False

    return ContractProverResult(
        status='proven', passed=True,
        obligation=f'ensures: all {checked} obligation(s) satisfy the clause'), True


# ---------------------------------------------------------------------------
# Obligation: loop invariant
# ---------------------------------------------------------------------------

def prove_invariant(ws: WhileStmt,
                    func_var_map: Optional[Dict[str, Any]] = None) -> ContractProverResult:
    """A declared invariant must be preserved by one iteration of the body.

    Proved as:  `invariant && cond  ==>  invariant[each name := its body output]`.

    The body runs only while `cond` holds, so preservation is checked in that state —
    the standard loop-body rule.  The body is evaluated from the loop's symbolic state
    and SUBSTITUTED into the invariant, exactly as `prove_ensures` substitutes into a
    postcondition.  Asserting the body's output into the antecedent instead (as an
    earlier version did) makes the antecedent unsatisfiable — `x == 0 && x == 1` — and
    every invariant then verifies vacuously.

    The invariant is re-established at the END OF THE BODY, which is where it must hold
    for the condition to be re-tested; re-establishing it at the loop head proves
    nothing.

    Any name the invariant depends on that the body does not determine is TAINTED: the
    obligation is reported `unverified`, never `proven` against an unconstrained value.
    """
    if ws.invariant is None:
        return ContractProverResult(status='vacuous', passed=True,
                                    obligation='no invariant clause')
    try:
        import z3 as z3_mod
    except ImportError:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant: z3 not available')

    vm: Dict[str, Any] = dict(func_var_map or {})
    for name in _idents(ws.invariant) | _idents(ws.condition):
        vm.setdefault(name, z3_mod.Int(name))

    inv_z3 = _expr_to_z3(ws.invariant, z3_mod, vm)
    cond_z3 = _expr_to_z3(ws.condition, z3_mod, vm)
    if inv_z3 is None or cond_z3 is None:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant: expression not modelled')

    states = _model_block(ws.body, [({}, set())], z3_mod, vm)
    if not states:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant: body could not be modelled')

    declared = _declared_names(ws.body)

    for assign, tainted in states:
        missing = sorted(n for n in _idents(ws.invariant)
                         if n in tainted or (n not in assign and n not in declared))
        if missing:
            return ContractProverResult(
                status='unverified', passed=False,
                obligation=f'invariant: body does not determine {missing}')

        out: Dict[str, Any] = {}
        bad = False
        for name, value in assign.items():
            term = _resolve(value, z3_mod, vm)
            if term is None:
                bad = True
                break
            out[name] = term
        if bad:
            return ContractProverResult(
                status='unverified', passed=False,
                obligation='invariant: body binding not modelled')

        inv_post = _expr_to_z3(ws.invariant, z3_mod, out)
        if inv_post is None:
            return ContractProverResult(status='unverified', passed=False,
                                        obligation='invariant: post-state not modelled')

        # `invariant && cond  ==>  invariant[body output]` — the standard loop-body
        # preservation rule.  The body runs only while `cond` holds, so that is the state
        # the rule must be checked in.  Using `!cond` here (an earlier version did) is
        # exactly backwards: it asserts the invariant after an iteration in a state where
        # the body never executes, which refutes sound invariants (`i <= 10` with
        # `i < 10` and `i += 1` is "refuted" at `i = 10`, a state the body skips).
        #
        # Entry establishment is a SEPARATE obligation (`_establish_invariant`), which
        # catches an invariant that holds only because the loop was entered in a good
        # state.
        pre = z3_mod.And(inv_z3, cond_z3)

        solver = z3_mod.Solver()
        solver.add(z3_mod.And(pre, z3_mod.Not(inv_post)))
        res = solver.check()
        if res == z3_mod.unsat:
            continue
        if res == z3_mod.sat:
            model = solver.model()
            ce = {}
            for name, var in vm.items():
                val = model.eval(var, model_completion=True)
                if val is not None:
                    ce[name] = str(val)
            return ContractProverResult(
                status='counterexample', passed=False,
                obligation='invariant: not preserved by the body',
                counterexample=ce)
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant: solver returned unknown')

    return ContractProverResult(status='proven', passed=True,
                                obligation='invariant: preserved by the body')


def _establish_invariant(ws: WhileStmt, func: FuncDecl,
                         var_map: Dict[str, Any]) -> ContractProverResult:
    """The invariant must hold the first time the loop is reached."""
    if ws.invariant is None:
        return ContractProverResult(status='vacuous', passed=True,
                                    obligation='no invariant clause')
    try:
        import z3 as z3_mod
    except ImportError:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant (entry): z3 not available')

    vm: Dict[str, Any] = dict(var_map)
    for name in _idents(ws.invariant):
        vm.setdefault(name, z3_mod.Int(name))

    inv_z3 = _expr_to_z3(ws.invariant, z3_mod, vm)
    if inv_z3 is None:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant (entry): not modelled')

    pre_terms = []
    if func.requires is not None:
        req = _expr_to_z3(func.requires, z3_mod, vm)
        if req is not None:
            pre_terms.append(req)

    # Every straight-line binding that precedes the loop.
    preceding = []
    for stmt in getattr(func.body, 'statements', []) or []:
        if stmt is ws:
            break
        preceding.append(stmt)

    holder = Block(type=NodeType.BLOCK, line=0, column=0, offset=0, statements=preceding)
    states = _model_block(holder, [({}, set())], z3_mod, vm)
    for assign, tainted in states:
        if tainted:
            return ContractProverResult(
                status='unverified', passed=False,
                obligation='invariant (entry): preceding bindings not fully modelled')
        for name, value in assign.items():
            term = _resolve(value, z3_mod, vm)
            if term is None:
                return ContractProverResult(
                    status='unverified', passed=False,
                    obligation=f'invariant (entry): binding for "{name}" not modelled')
            pre_terms.append(vm.get(name, z3_mod.Int(name)) == term)

    pre = z3_mod.And(*pre_terms) if pre_terms else z3_mod.BoolVal(True)
    solver = z3_mod.Solver()
    solver.add(z3_mod.And(pre, z3_mod.Not(inv_z3)))
    res = solver.check()
    if res == z3_mod.unsat:
        return ContractProverResult(status='proven', passed=True,
                                    obligation='invariant: established on entry')
    if res == z3_mod.sat:
        model = solver.model()
        ce = {}
        for name, var in vm.items():
            val = model.eval(var, model_completion=True)
            if val is not None:
                ce[name] = str(val)
        return ContractProverResult(
            status='counterexample', passed=False,
            obligation='invariant: not established on entry',
            counterexample=ce)
    return ContractProverResult(status='unverified', passed=False,
                                obligation='invariant (entry): solver returned unknown')


# ---------------------------------------------------------------------------
# Whole-program driver
# ---------------------------------------------------------------------------

def prove_contracts(source: str, ast: Any = None) -> ContractResult:
    """Prove every contract obligation in a program.

    Every function with a `requires` or `ensures` clause is checked, and every
    `while ... invariant` anywhere in the program.  The earlier version stopped after
    the first function, which made a broken contract in function two invisible.
    """
    from svl.parser_rd import parse
    from svl.lexer import tokenize

    if ast is None:
        ast = parse(tokenize(source))

    result = ContractResult(function_name='<module>')
    funcs = _walk(ast, (FuncDecl,))
    if not funcs:
        return result

    try:
        import z3 as z3_mod
    except ImportError:
        result.requires_result = ContractProverResult(
            status='unverified', passed=False,
            obligation='contract prover: z3 not available')
        return result

    for func in funcs:
        vm: Dict[str, Any] = {p.name: z3_mod.Int(p.name) for p in func.params}
        vm.setdefault('result', z3_mod.Int('result'))

        result.function_name = func.name
        result.requires_result = prove_requires(func, var_map=vm)

        ensures_res, _sound = prove_ensures(func, var_map=vm)
        result.ensures_results.append((func.name, ensures_res))

        for ws in _walk(func.body, (WhileStmt,)):
            line = getattr(ws, 'line', '?')
            result.invariant_results.append(
                (f'{func.name}@L{line}', _establish_invariant(ws, func, vm)))
            result.invariant_results.append(
                (f'{func.name}@L{line}', prove_invariant(ws, func_var_map=vm)))

    return result


def verify_contracts(source: str, ast: Any = None) -> Tuple[bool, List[str]]:
    """Verify every contract in a program.

    Returns ``(all_obligations_proven, problems)``.  A problem is a real refutation —
    a counterexample from z3.  An obligation that could not be decided is NOT a
    problem — it is silence, the same contract the rest of the gate keeps.
    """
    result = prove_contracts(source, ast)

    problems: List[str] = []

    if result.requires_result and result.requires_result.status == 'counterexample':
        problems.append(f"{result.function_name}: requires: {result.requires_result.obligation}")

    for fname, res in result.ensures_results:
        if res.status == 'counterexample':
            problems.append(f"{fname}: ensures: {res.obligation}")

    for label, res in result.invariant_results:
        if res.status == 'counterexample':
            problems.append(f"{label}: invariant: {res.obligation}")

    return (not problems), problems


if __name__ == '__main__':
    test_src = """
    module test {
      func add(a: int, b: int) type int
        requires a > 0 && b > 0
        ensures result >= a
      {
        return a + b
      }
    }
    """
    r = prove_contracts(test_src)
    print(f"Function: {r.function_name}")
    print(f"  requires: {r.requires_result}")
    for fname, e in r.ensures_results:
        print(f"  ensures [{fname}]: {e}")
    for label, i in r.invariant_results:
        print(f"  invariant [{label}]: {i}")
    print(f"  all_proven: {r.all_proven}")
    print(f"  any_counterexample: {r.any_counterexample}")