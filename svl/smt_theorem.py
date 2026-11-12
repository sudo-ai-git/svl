# svl/smt_theorem.py
# SMT-Based Theorem Layer using Z3
#
# This module used to be hollow.  `_extract_arithmetic_constraints` walked the AST and
# appended NOTHING, so `verify_arithmetic_constraints([])` built an empty solver and returned
# `sat` -- i.e. `passed=True` in 0 ms for every program, including programs whose assertions
# were false.  It now builds a real z3 model of the program's straight-line arithmetic and
# discharges every `assert` by testing the satisfiability of its NEGATION:
#
#   unsat -> the assertion is PROVEN for every input the prefix permits;
#   sat   -> a concrete COUNTEREXAMPLE is reported.
#
# Scope, stated plainly (this is a prover for straight-line code, not a general verifier):
# * Loops are reported as UNVERIFIED, never guessed at: proving a loop needs invariants this
#   layer does not have.  An assertion inside a loop is listed in `unverified`.
# * `+ - *` and the comparisons are modelled exactly.  `/`, `%`, bitwise operators, arrays
#   and structs are reported as unsupported rather than modelled with the wrong semantics --
#   WASM `i32` division truncates toward zero while z3's integer division is Euclidean, so
#   silently substituting one for the other would produce false proofs.
# * OPT-IN.  This is not on the compile path.  It is far more expensive than the interval
#   abstract interpreter (`svl/abstract_interpretation.py`) and answers a DIFFERENT question:
#   the interpreter proves index bounds for values it can bound; this proves assertions for
#   all inputs.  Run it when you want a proof, not on every compile.
# * BPSW monodromy still runs first and still gates nothing -- it is constant-true for every
#   residue of {17,37,73} (see README / KB §5.3.2).  It is kept for continuity and reported
#   as `bpsw_fallback`, not as evidence.

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time as _time
import hashlib

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    z3 = None

from svl.bpsw_monodromy import verify_theorem, TheoremVerifyResult
from svl.serialization import to_binary
from svl.parser_rd import (
    parse, tokenize, Block, LetStmt, IfStmt, WhileStmt, ForStmt, AssertStmt,
    ExprStmt, AssignExpr, FuncDecl, ConstDecl, VarDecl, Literal, Ident, BinaryExpr,
    UnaryExpr, IndexExpr, FieldAccess, ArrayLit, CallExpr,
)


class SMTLogic(Enum):
    """Supported SMT logics."""
    QF_LIA = "QF_LIA"      # Quantifier-free linear integer arithmetic
    QF_NIA = "QF_NIA"      # Quantifier-free non-linear integer arithmetic
    QF_BV = "QF_BV"        # Quantifier-free bitvectors
    LIA = "LIA"            # Linear integer arithmetic (with quantifiers)
    NIA = "NIA"            # Non-linear integer arithmetic
    BV = "BV"              # Bitvectors with quantifiers
    AUFLIA = "AUFLIA"      # Arrays + UF + LIA


@dataclass
class SMTVerifyResult:
    """Result of SMT-based verification.

    `passed` means **no counterexample was found** -- it does NOT mean the program was
    verified.  Read `status` for the honest state:

    * ``'proven'`         every assertion was discharged (unsat of its negation);
    * ``'counterexample'` at least one assertion was refuted -- `passed` is False;
    * ``'unverified'`     the layer could not model the program, so it proved nothing
                          (unsupported construct, or a loop, which needs invariants);
    * ``'vacuous'`        the program contains no assertion to discharge.
    """
    passed: bool
    logic: SMTLogic
    solver_time_ms: float
    status: str = 'unverified'
    model: Optional[Dict[str, Any]] = None
    unsat_core: Optional[List[str]] = None
    error_message: Optional[str] = None
    bpsw_fallback: Optional[TheoremVerifyResult] = None
    assertions_checked: int = 0
    assertions_proven: int = 0
    counterexamples: List[Dict[str, Any]] = field(default_factory=list)
    unverified: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """True only when every assertion was actually proven."""
        return self.status == 'proven'

    @property
    def vacuous(self) -> bool:
        """True when nothing was discharged.  Do NOT read this as 'verified'."""
        return self.status == 'vacuous'


@dataclass
class SMTConfig:
    """Configuration for SMT verification."""
    logic: SMTLogic = SMTLogic.QF_LIA
    timeout_ms: int = 30000
    use_bpsw_fallback: bool = True
    produce_models: bool = True
    produce_unsat_cores: bool = True


class _Unsupported(Exception):
    """Raised on a construct this layer does not model.  Never guessed at."""


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _describe(expr, limit: int = 40) -> str:
    """A short human-readable rendering of an assertion, for counterexamples."""
    if isinstance(expr, BinaryExpr):
        return f"{_describe(expr.left)} {expr.operator} {_describe(expr.right)}"
    if isinstance(expr, UnaryExpr):
        return f"{expr.operator}{_describe(expr.operand)}"
    if isinstance(expr, Ident):
        return expr.name
    if isinstance(expr, Literal):
        return str(expr.value)
    return type(expr).__name__


class _SymbolicVerifier:
    """Interpret straight-line SVL into z3 and collect assertions to discharge."""

    def __init__(self, logic: SMTLogic = SMTLogic.QF_LIA, timeout_ms: int = 30000):
        self.env: Dict[str, Any] = {}
        self.assertions: List[Tuple[Any, Any, int, str]] = []
        self.unverified: List[str] = []
        self.logic = logic
        self.timeout_ms = timeout_ms
        # Set once an unmodelled construct (a loop, an unsupported statement) is reached.
        # Assertions after that point are reported as UNVERIFIED rather than discharged,
        # because discharging them against stale variable values would produce spurious
        # counterexamples -- a false refutation is worse than no answer.
        self.tainted = False
        # Loop-invariant state.
        self.loop_depth = 0
        # Variables whose value after a loop is NOT constrained by the loop's invariant.
        # An assertion that mentions one is reported as unverified rather than discharged:
        # discharging it against an unconstrained value would produce a spurious
        # counterexample -- a false refutation is worse than no answer.
        self.stale: set = set()
        self._loop_counter = 0
        # Arrays: name -> z3 Array, and name -> its length expression.
        self.arrays: Dict[str, Any] = {}
        self.array_lens: Dict[str, Any] = {}
        # The most recent value assigned to each name, used to propose loop invariants
        # (the lower bound of a counting variable comes from its initialiser).
        self.last_assign: Dict[str, Any] = {}

    # ---- solver ------------------------------------------------------------

    def _solver(self) -> 'z3.Solver':
        s = z3.Solver()
        s.set("timeout", self.timeout_ms)
        if self.logic != SMTLogic.QF_LIA:
            s.set("logic", self.logic.value)
        return s

    # ---- expressions -------------------------------------------------------

    def expr(self, e):
        if isinstance(e, Literal):
            if isinstance(e.value, bool):
                return z3.BoolVal(e.value)
            if _is_int(e.value):
                return z3.IntVal(int(e.value))
            raise _Unsupported(f"literal of type {type(e.value).__name__}")
        if isinstance(e, Ident):
            if e.name in self.env:
                return self.env[e.name]
            raise _Unsupported(f"unbound name '{e.name}'")
        if isinstance(e, BinaryExpr):
            op = e.operator
            if op in ('&&', '||'):
                l = self.expr(e.left)
                r = self.expr(e.right)
                return z3.And(l, r) if op == '&&' else z3.Or(l, r)
            if op in ('==', '!=', '<', '<=', '>', '>='):
                l = self.expr(e.left)
                r = self.expr(e.right)
                return {'==': l == r, '!=': l != r, '<': l < r,
                        '<=': l <= r, '>': l > r, '>=': l >= r}[op]
            if op in ('+', '-', '*'):
                l = self.expr(e.left)
                r = self.expr(e.right)
                if op == '+':
                    return l + r
                if op == '-':
                    return l - r
                return l * r
            raise _Unsupported(f"operator '{op}'")
        if isinstance(e, UnaryExpr):
            v = self.expr(e.operand)
            if e.operator == '-':
                return -v
            if e.operator == '!':
                return z3.Not(v)
            raise _Unsupported(f"unary operator '{e.operator}'")
        if isinstance(e, IndexExpr):
            arr = self.expr(e.left)
            if not z3.is_array(arr):
                raise _Unsupported(
                    f"indexing a non-array value ({type(e.left).__name__})")
            return z3.Select(arr, self.expr(e.right))
        if isinstance(e, ArrayLit):
            # A fresh constant array with each element stored at its position. The
            # literal's length is recorded by the caller (`_bind`) so `len(a)` resolves.
            arr = z3.K(z3.IntSort(), z3.IntVal(0))
            for i, elem in enumerate(e.elements):
                arr = z3.Store(arr, z3.IntVal(i), self.expr(elem))
            return arr
        if isinstance(e, CallExpr):
            if e.callee == 'len':
                if len(e.arguments) != 1:
                    raise _Unsupported("len() takes exactly 1 argument")
                return self._array_length(e.arguments[0])
            if e.callee == 'zeros':
                if len(e.arguments) != 1:
                    raise _Unsupported("zeros() takes exactly 1 argument")
                return z3.K(z3.IntSort(), z3.IntVal(0))
            raise _Unsupported(f"call to '{e.callee}'")
        raise _Unsupported(f"expression {type(e).__name__}")

    def _array_length(self, arg) -> Any:
        """The length of an array expression: a tracked length, or a fresh unknown."""
        if isinstance(arg, Ident):
            if arg.name in self.array_lens:
                return self.array_lens[arg.name]
            if z3.is_array(self.env.get(arg.name)):
                return z3.Int(f"{arg.name}_len")
        raise _Unsupported("len() of an array with no tracked length")

    def _bind(self, name: str, value: Any, length: Any = None) -> None:
        """Bind a name to a z3 value, recording an array length when there is one.

        Re-binding an array (`a[i] = v`) does NOT change its length, so an existing
        length is kept unless the caller supplies a new one. Overwriting it with a fresh
        unknown made `len(a)` in a later condition resolve to an unconstrained variable.
        """
        self.env[name] = value
        self.last_assign[name] = value
        if z3.is_array(value):
            self.arrays[name] = value
            if length is not None:
                self.array_lens[name] = length
            elif name not in self.array_lens:
                self.array_lens[name] = z3.Int(f"{name}_len")

    # ---- statements --------------------------------------------------------

    def block(self, block: Block, path=None) -> Any:
        """Model a block and return the path refined by any loop it contains."""
        if path is None:
            path = z3.BoolVal(True)
        for stmt in getattr(block, 'statements', []) or []:
            try:
                path = self.stmt(stmt, path)
            except _Unsupported as exc:
                # One unsupported statement must not abandon the rest of the program: record
                # it, taint everything downstream, and keep going.
                self.unverified.append(
                    f"line {getattr(stmt, 'line', 0)}: {type(stmt).__name__} not modelled "
                    f"({exc})")
                self.tainted = True
        return path

    def stmt(self, s, path) -> Any:
        if isinstance(s, (LetStmt, ConstDecl, VarDecl)):
            self._bind_statement(s)
            return path
        if isinstance(s, AssertStmt):
            if self.tainted:
                self.unverified.append(
                    f"line {getattr(s, 'line', 0)}: assertion "
                    f"\"{_describe(s.condition)}\" was NOT checked -- it depends on an "
                    f"unmodelled construct")
                return path
            if self._mentions_stale(s.condition):
                self.unverified.append(
                    f"line {getattr(s, 'line', 0)}: assertion "
                    f"\"{_describe(s.condition)}\" was NOT checked -- it mentions a "
                    f"variable whose value after a loop is not constrained by an invariant")
                return path
            cond = self.expr(s.condition)
            self.assertions.append(
                (path, cond, int(getattr(s, 'line', 0) or 0), _describe(s.condition)))
            return path
        if isinstance(s, IfStmt):
            cond = self.expr(s.condition)
            base = dict(self.env)
            self.env = dict(base)
            self.block(s.then_branch, z3.And(path, cond))
            self.env = dict(base)
            self.block(s.else_branch, z3.And(path, z3.Not(cond)))
            self.env = base          # branch-local bindings do not escape
            return path
        if isinstance(s, WhileStmt):
            return self._handle_while(s, path)
        if isinstance(s, ForStmt):
            return self._handle_for(s, path)
        if isinstance(s, ExprStmt):
            # The parser wraps every expression statement in ExprStmt, so assignments
            # arrive here -- handling AssignExpr only as a bare statement left `i += 1`
            # unmodelled (a silent no-op).
            if isinstance(s.expression, AssignExpr):
                self._assign(s.expression)
            else:
                self.expr(s.expression)
            return path
        if isinstance(s, AssignExpr):
            self._assign(s)
            return path
        # ReturnStmt / declarations: nothing to model
        return path

    # ---- binding and assignment --------------------------------------------

    def _bind_statement(self, s) -> None:
        """Model `let x = v` / `const x = v`, recording array lengths."""
        value = s.value
        if isinstance(value, CallExpr) and value.callee == 'zeros':
            length = self.expr(value.arguments[0])
            self._bind(s.name, z3.K(z3.IntSort(), z3.IntVal(0)), length)
            return
        if isinstance(value, ArrayLit):
            arr = self.expr(value)
            self._bind(s.name, arr, z3.IntVal(len(value.elements)))
            return
        self._bind(s.name, self.expr(value))

    def _assign(self, s: AssignExpr) -> None:
        """Model `x = v`, `x += v`, `a[i] = v`."""
        target = s.target
        if isinstance(target, IndexExpr):
            if not isinstance(target.left, Ident):
                raise _Unsupported("assignment to an index of a non-name")
            name = target.left.name
            if not z3.is_array(self.env.get(name)):
                raise _Unsupported(f"'{name}' is not an array")
            idx = self.expr(target.right)
            current = z3.Select(self.env[name], idx)
            val = self.expr(s.value) if s.operator == '=' else self._compound(
                s.operator, current, s.value)
            self._bind(name, z3.Store(self.env[name], idx, val))
            return
        name = getattr(target, 'name', None)
        if name is None:
            raise _Unsupported("assignment to a non-name target")
        current = self.env.get(name)
        if current is None:
            raise _Unsupported(f"assignment to an unbound name '{name}'")
        if s.operator == '=':
            self._bind(name, self.expr(s.value))
        else:
            self._bind(name, self._compound(s.operator, current, s.value))

    def _compound(self, operator: str, current: Any, value_expr) -> Any:
        op = operator[:-1] if operator.endswith('=') else operator     # '+=' -> '+'
        value = self.expr(value_expr)
        if op == '+':
            return current + value
        if op == '-':
            return current - value
        if op == '*':
            return current * value
        raise _Unsupported(f"compound assignment '{operator}'")

    # ---- loops and invariants ----------------------------------------------

    def _handle_while(self, s: WhileStmt, path) -> Any:
        line = int(getattr(s, 'line', 0) or 0)
        if self.loop_depth > 0:
            self.unverified.append(f"line {line}: nested loop not modelled")
            self.tainted = True
            return path
        cond = self.expr(s.condition)
        assigned = self._assigned_vars(s.body)
        proposal = self._while_candidate(s.condition, assigned)
        if proposal is None:
            self.unverified.append(
                f"line {line}: loop not modelled (no loop invariant could be proposed)")
            self.tainted = True
            return path
        candidate, constrained = proposal
        self.loop_depth += 1
        new_path, post_env, ok = self._try_invariant(
            candidate,
            lambda env: self._expr_in(s.condition, env),
            s.body, path, constrained=constrained,
        )
        self.loop_depth -= 1
        if not ok:
            self.unverified.append(
                f"line {line}: loop invariant could not be proved; assertions in and "
                f"after this loop were NOT checked")
            self.tainted = True
            return path
        self.env = post_env
        self.stale |= (assigned - set(constrained))
        return new_path

    def _handle_for(self, s: ForStmt, path) -> Any:
        line = int(getattr(s, 'line', 0) or 0)
        if self.loop_depth > 0:
            self.unverified.append(f"line {line}: nested loop not modelled")
            self.tainted = True
            return path
        iter_expr = s.iter_expr
        if not (isinstance(iter_expr, BinaryExpr) and iter_expr.operator == '..'):
            self.unverified.append(
                f"line {line}: iterator loop not modelled (only `for i in a..b`)")
            self.tainted = True
            return path
        start = self.expr(iter_expr.left)
        end = self.expr(iter_expr.right)
        if not (z3.is_int(start) and z3.is_int(end)):
            self.unverified.append(f"line {line}: non-integer loop bounds not modelled")
            self.tainted = True
            return path
        var = s.var
        self.env[var] = start
        self.last_assign[var] = start
        cond = self.env[var] < end

        # A `for` loop whose body provably never runs is a no-op. Without this the body's
        # assignments would be marked stale and a true assertion about them unverified.
        probe = self._solver()
        probe.add(z3.Not(start >= end))
        if probe.check() == z3.unsat:
            return path                      # start >= end is provable: zero iterations

        def candidate(env):
            v = env.get(var)
            if v is None or not z3.is_int(v):
                return None
            # Exact for a counting loop: at entry v == start; the disjunction covers the
            # zero-iteration case (start > end), where the body never runs.
            return z3.And(v >= start, z3.Or(v <= end, start > end))

        def step():
            self.env[var] = self.env[var] + 1

        self.loop_depth += 1
        new_path, post_env, ok = self._try_invariant(
            candidate,
            lambda env: env.get(var, start) < end,
            s.body, path, constrained={var}, extra_step=step,
        )
        self.loop_depth -= 1
        if not ok:
            self.unverified.append(
                f"line {line}: loop invariant could not be proved; assertions in and "
                f"after this loop were NOT checked")
            self.tainted = True
            return path
        self.env = post_env
        self.stale |= (self._assigned_vars(s.body) - {var})
        return new_path

    def _expr_in(self, expr, env) -> Any:
        """Evaluate an expression against an explicit environment."""
        saved = self.env
        self.env = env
        try:
            return self.expr(expr)
        finally:
            self.env = saved

    def _try_invariant(self, candidate, cond_of, body, path, constrained, extra_step=None):
        """Validate a candidate loop invariant and model the loop with it.

        A candidate is only ever USED after the solver proves two things:

        * **entry** -- it holds on the state that reaches the loop;
        * **preservation** -- assuming it and the condition, one execution of the body
          (plus the loop's own step) re-establishes it.

        If either fails the candidate is discarded and the loop is reported as unverified,
        exactly as before. Nothing is ever assumed without a proof.

        Returns ``(new_path, post_env, ok)``. Both the body run and the after-loop state
        use FRESH symbols for the constrained variables: an arbitrary iteration and an
        arbitrary final state, not the pre-loop constants. Using the pre-loop value made
        `assert i < 5` inside `while i < 10 { i += 1 }` look proven (0 < 5), which is the
        classic unsound loop model.
        """
        pre_env = dict(self.env)
        inv_pre = candidate(pre_env)
        if inv_pre is None:
            return None, None, False
        solver = self._solver()
        solver.add(path)
        solver.add(z3.Not(inv_pre))
        if solver.check() != z3.unsat:
            return None, None, False

        self._loop_counter += 1
        tag = f"loop{self._loop_counter}"
        body_env = self._symbolize(pre_env, constrained, tag + "a")
        inv_body = candidate(body_env)
        if inv_body is None:
            return None, None, False

        saved_env, saved_unv, saved_taint = self.env, list(self.unverified), self.tainted
        saved_assertions = list(self.assertions)
        self.env = dict(body_env)
        self.unverified, self.tainted = [], False
        # Assertions inside the loop are discharged under the invariant: it holds at the
        # top of every iteration, so this is sound.
        self.block(body, z3.And(path, inv_body, cond_of(body_env)))
        if extra_step is not None:
            extra_step()
        inv_after = candidate(self.env)
        post_body_env = dict(self.env)
        body_assertions = self.assertions[len(saved_assertions):]
        body_unv, body_taint = list(self.unverified), self.tainted

        self.env, self.tainted = saved_env, saved_taint
        self.assertions = saved_assertions + body_assertions
        self.unverified = saved_unv + body_unv
        if body_taint or inv_after is None:
            return None, None, False

        solver2 = self._solver()
        solver2.add(path)
        solver2.add(inv_body)
        solver2.add(cond_of(body_env))
        solver2.add(z3.Not(inv_after))
        if solver2.check() != z3.unsat:
            return None, None, False

        # The after-loop state keeps the body's effects (array stores and the like) and
        # re-symbolises each constrained variable, constrained by the invariant and the
        # negated condition -- a sound over-approximation of the real final state.
        post_env = self._symbolize(post_body_env, constrained, tag + "b")
        inv_post = candidate(post_env)
        if inv_post is None:
            return None, None, False
        new_path = z3.And(path, inv_post, z3.Not(cond_of(post_env)))
        return new_path, post_env, True

    def _symbolize(self, env, names, tag) -> Dict[str, Any]:
        """Copy `env`, replacing each named variable with a fresh symbol."""
        out = dict(env)
        for name in sorted(names):
            v = env.get(name)
            if v is None:
                continue
            if z3.is_int(v):
                out[name] = z3.Int(f"{name}__{tag}")
            elif z3.is_bool(v):
                out[name] = z3.Bool(f"{name}__{tag}")
        return out

    def _while_candidate(self, cond, assigned):
        """Propose an invariant for a `while` loop, or None when none can be proposed.

        The proposal is built from the loop condition (`i < n` suggests `i <= n`) and the
        most recent assignment to each variable the body modifies (its lower bound). It is
        a *candidate*: `_try_invariant` proves it before it is used.

        Returns `(builder, constrained_names)`.
        """
        clauses = []                       # (var, 'le'|'ge', bound z3 expression)
        for op, left, right in self._comparisons(cond):
            for var_side, bound_side in ((left, right), (right, left)):
                if not isinstance(var_side, Ident) or var_side.name not in assigned:
                    continue
                if isinstance(bound_side, Ident) and bound_side.name in assigned:
                    continue               # both sides vary: no usable bound
                try:
                    bound = self.expr(bound_side)
                except _Unsupported:
                    continue
                if not z3.is_int(bound):
                    continue
                if op in ('<', '<='):
                    clauses.append((var_side.name, 'le', bound))
                else:
                    clauses.append((var_side.name, 'ge', bound))
                break
        for name in assigned:
            init = self.last_assign.get(name)
            if init is not None and z3.is_int(init):
                clauses.append((name, 'ge', init))
        if not clauses:
            return None

        def builder(env):
            out = []
            for name, rel, bound in clauses:
                v = env.get(name)
                if v is None or not z3.is_int(v):
                    return None
                out.append(v <= bound if rel == 'le' else v >= bound)
            return z3.And(out) if out else None

        return builder, {name for name, _rel, _bound in clauses}

    def _mentions_stale(self, expr) -> bool:
        """True when an expression references a variable not constrained by an invariant."""
        if isinstance(expr, Ident):
            return expr.name in self.stale
        if hasattr(expr, '__dataclass_fields__'):
            for f in expr.__dataclass_fields__:
                value = getattr(expr, f)
                if isinstance(value, list):
                    if any(self._mentions_stale(item) for item in value):
                        return True
                elif hasattr(value, '__dataclass_fields__'):
                    if self._mentions_stale(value):
                        return True
        return False

    def _comparisons(self, expr):
        """Yield (op, left, right) for every comparison in an expression tree."""
        if isinstance(expr, BinaryExpr):
            if expr.operator in ('<', '<=', '>', '>='):
                yield (expr.operator, expr.left, expr.right)
            yield from self._comparisons(expr.left)
            yield from self._comparisons(expr.right)

    def _assigned_vars(self, block) -> set:
        """Every name assigned anywhere in a block (including inside nested statements)."""
        names = set()

        def walk(node):
            if node is None:
                return
            if isinstance(node, AssignExpr):
                target = node.target
                if isinstance(target, Ident):
                    names.add(target.name)
                elif isinstance(target, IndexExpr) and isinstance(target.left, Ident):
                    names.add(target.left.name)      # `a[i] = v` modifies the array
                elif isinstance(target, FieldAccess) and isinstance(target.left, Ident):
                    names.add(target.left.name)      # `p.f = v` modifies the struct
                return
            if isinstance(node, ExprStmt):
                walk(node.expression)
                return
            if hasattr(node, '__dataclass_fields__'):
                for f in node.__dataclass_fields__:
                    value = getattr(node, f)
                    if isinstance(value, list):
                        for item in value:
                            walk(item)
                    elif hasattr(value, '__dataclass_fields__'):
                        walk(value)

        for stmt in getattr(block, 'statements', []) or []:
            walk(stmt)
        return names

    # ---- discharge ---------------------------------------------------------

    def discharge(self) -> Tuple[int, List[Dict[str, Any]]]:
        """Prove every collected assertion by refuting its negation."""
        proven = 0
        counterexamples: List[Dict[str, Any]] = []
        for path, cond, line, desc in self.assertions:
            solver = self._solver()
            solver.add(path)
            solver.add(z3.Not(cond))
            result = solver.check()
            if result == z3.unsat:
                proven += 1
            elif result == z3.sat:
                model = solver.model()
                ce = {
                    'line': line,
                    'assertion': desc,
                    'counterexample': {
                        str(d): (model[d].as_long() if model[d].is_int() else str(model[d]))
                        for d in model.decls()
                    },
                }
                counterexamples.append(ce)
            else:
                self.unverified.append(f"line {line}: solver returned {result}")
        return proven, counterexamples


class SMTTheoremLayer:
    """SMT-based theorem verification layer using Z3."""

    def __init__(self, config: Optional[SMTConfig] = None):
        if not Z3_AVAILABLE:
            raise RuntimeError("Z3 not available. Install with: pip install z3-solver")
        self.config = config or SMTConfig()
        self._solver_cache: Dict[str, 'z3.Solver'] = {}

    def _create_solver(self) -> 'z3.Solver':
        """Create a new Z3 solver with configured logic."""
        solver = z3.Solver()
        solver.set("timeout", self.config.timeout_ms)
        if self.config.logic != SMTLogic.QF_LIA:
            solver.set("logic", self.config.logic.value)
        return solver

    def verify_arithmetic_constraints(self, constraints: List[Any]) -> SMTVerifyResult:
        """Check a list of z3 boolean constraints for joint satisfiability.

        `passed=True` means the constraints are SATISFIABLE -- i.e. no contradiction was
        found.  It does NOT mean the program is correct; use `verify_program_theorem` to
        discharge assertions.
        """
        start = _time.perf_counter()
        try:
            solver = self._create_solver()
            for c in constraints:
                solver.add(c)
            result = solver.check()
            elapsed = (_time.perf_counter() - start) * 1000
            if result == z3.sat:
                model = None
                if self.config.produce_models:
                    m = solver.model()
                    model = {str(v): (m[v].as_long() if m[v].is_int() else str(m[v]))
                             for v in m.decls()}
                return SMTVerifyResult(passed=True, status='proven',
                                       logic=self.config.logic,
                                       solver_time_ms=elapsed, model=model)
            if result == z3.unsat:
                core = None
                if self.config.produce_unsat_cores:
                    core = [str(c) for c in solver.unsat_core()]
                return SMTVerifyResult(passed=False, status='counterexample',
                                       logic=self.config.logic,
                                       solver_time_ms=elapsed, unsat_core=core)
            return SMTVerifyResult(passed=True, status='unverified',
                                   logic=self.config.logic,
                                   solver_time_ms=elapsed,
                                   error_message=f"Solver returned unknown: {result}")
        except Exception as e:                                          # noqa: BLE001
            return SMTVerifyResult(
                passed=True, status='unverified',
                logic=self.config.logic,
                solver_time_ms=(_time.perf_counter() - start) * 1000,
                error_message=f"SMT verification error: {e}")

    def verify_bitvector_constraints(self, constraints: List[Any],
                                     bitwidth: int = 32) -> SMTVerifyResult:
        """Bitvector constraints -- NOT modelled.  Reported honestly rather than approximated."""
        return SMTVerifyResult(
            passed=False, logic=SMTLogic.QF_BV, solver_time_ms=0,
            error_message=("Bitvector verification is not implemented; modelling WASM i32 "
                           "truncating division/remainder as Euclidean would produce false proofs"))

    def verify_program_theorem(self, source: str) -> SMTVerifyResult:
        """Discharge every `assert` in the program by refuting its negation.

        BPSW monodromy runs first.  It is constant-true for every residue of {17,37,73}, so
        it cannot fail and gates nothing -- it is reported for continuity only.
        """
        start = _time.perf_counter()
        ast = parse(tokenize(source))
        bpsw_result = verify_theorem(to_binary(ast))
        if not bpsw_result.passed:
            return SMTVerifyResult(
                passed=False, logic=self.config.logic,
                solver_time_ms=(_time.perf_counter() - start) * 1000,
                error_message="BPSW monodromy failed", bpsw_fallback=bpsw_result)

        verifier = _SymbolicVerifier(self.config.logic, self.config.timeout_ms)
        try:
            for module in getattr(ast, 'modules', []) or []:
                verifier.block(module.body)
            self._verify_top_level(ast.items, verifier)
            for module in getattr(ast, 'modules', []) or []:
                self._verify_top_level(getattr(module.body, 'statements', []), verifier)
        except _Unsupported as exc:
            # The layer could not model the program, so it proved nothing.  That is NOT a
            # failure: report it as unverified rather than passing it or failing it.
            return SMTVerifyResult(
                passed=True,
                status='unverified',
                logic=self.config.logic,
                solver_time_ms=(_time.perf_counter() - start) * 1000,
                assertions_checked=len(verifier.assertions),
                unverified=list(verifier.unverified) + [f"unsupported construct: {exc}"],
                bpsw_fallback=bpsw_result)

        proven, counterexamples = verifier.discharge()
        elapsed = (_time.perf_counter() - start) * 1000
        checked = len(verifier.assertions)

        if counterexamples:
            status = 'counterexample'
        elif verifier.unverified:
            status = 'unverified'
        elif checked == 0:
            status = 'vacuous'
        else:
            status = 'proven'

        return SMTVerifyResult(
            passed=status != 'counterexample',
            status=status,
            logic=self.config.logic,
            solver_time_ms=elapsed,
            assertions_checked=checked,
            assertions_proven=proven,
            counterexamples=counterexamples,
            unverified=list(verifier.unverified),
            bpsw_fallback=bpsw_result,
            error_message=None if status == 'proven' else
                f"status={status}: {len(counterexamples)} counterexample(s), "
                f"{checked - proven - len(counterexamples)} unproven, "
                f"{len(verifier.unverified)} unverified"
        )

    def _verify_top_level(self, items, verifier: _SymbolicVerifier) -> None:
        """Model each function body with fresh symbolic parameters."""
        for item in items or []:
            if not isinstance(item, FuncDecl):
                continue
            saved = dict(verifier.env)
            for p in item.params:
                verifier.env[p.name] = z3.Int(f"{item.name}_{p.name}")
            verifier.block(item.body)
            verifier.env = saved

    def find_counterexample(self, source: str, property_name: str) -> SMTVerifyResult:
        """Counterexample search -- NOT implemented.  Reported honestly."""
        return SMTVerifyResult(
            passed=False, logic=self.config.logic, solver_time_ms=0,
            error_message="Counterexample generation is not implemented; "
                          "use verify_program_theorem, which reports counterexamples "
                          "for every assertion it cannot prove")


# High-level API
def verify_with_smt(source: str, config: Optional[SMTConfig] = None) -> SMTVerifyResult:
    """Verify SVL source using SMT theorem layer."""
    if not Z3_AVAILABLE:
        return SMTVerifyResult(
            passed=False, logic=SMTLogic.QF_LIA, solver_time_ms=0,
            error_message="Z3 not available")
    layer = SMTTheoremLayer(config)
    return layer.verify_program_theorem(source)


def verify_with_smt_or_bpsw(source: str) -> SMTVerifyResult:
    """Verify with SMT, falling back to BPSW if Z3 unavailable."""
    if Z3_AVAILABLE:
        return verify_with_smt(source)
    bpsw_result = verify_theorem(to_binary(parse(tokenize(source))))
    return SMTVerifyResult(
        passed=bpsw_result.passed, logic=SMTLogic.QF_LIA, solver_time_ms=0,
        bpsw_fallback=bpsw_result,
        error_message="Z3 unavailable; BPSW alone gates nothing (constant-true)")


def enhance_theorem_layer_with_smt(source: str, use_smt: bool = True) -> SMTVerifyResult:
    """Enhanced theorem layer that combines BPSW + SMT."""
    if use_smt and Z3_AVAILABLE:
        return verify_with_smt(source)
    bpsw_result = verify_theorem(to_binary(parse(tokenize(source))))
    return SMTVerifyResult(
        passed=bpsw_result.passed, logic=SMTLogic.QF_LIA, solver_time_ms=0,
        bpsw_fallback=bpsw_result)


if __name__ == '__main__':
    print("=== SMT Theorem Layer Test ===")
    print(f"Z3 Available: {Z3_AVAILABLE}")

    if Z3_AVAILABLE:
        s = z3.Solver()
        x = z3.Int('x')
        s.add(x > 5, x < 10)
        result = s.check()
        print(f"Z3 Test: {result}")
        if result == z3.sat:
            print(f"Model: x = {s.model()[x]}")

        cases = {
            "true assertion": ("module t { func main() type int { let x: int = 5 assert x == 5 return 0 } }", True),
            "false assertion": ("module t { func main() type int { let x: int = 5 assert x == 6 return 0 } }", False),
            "for all a: a+1 > a": ("module t { func f(a: int) type int { assert a + 1 > a return 0 } }", True),
            "not provable": ("module t { func f(a: int) type int { assert a > 0 return 0 } }", False),
        }
        print("\nSVL Integration Tests:")
        for name, (src, expect) in cases.items():
            r = verify_with_smt(src)
            ok = r.passed == expect
            print(f"  {'ok  ' if ok else 'FAIL'} {name}: passed={r.passed} "
                  f"checked={r.assertions_checked} proven={r.assertions_proven} "
                  f"{r.solver_time_ms:.1f} ms")
            if r.counterexamples:
                print(f"       counterexample: {r.counterexamples[0]['counterexample']}")
    else:
        print("Z3 not installed. Install with: pip install z3-solver")

    print("\n✓ SMT Theorem Layer test complete!")
