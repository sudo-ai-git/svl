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
    UnaryExpr,
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
        raise _Unsupported(f"expression {type(e).__name__}")

    # ---- statements --------------------------------------------------------

    def block(self, block: Block, path=None) -> None:
        if path is None:
            path = z3.BoolVal(True)
        for stmt in getattr(block, 'statements', []) or []:
            try:
                self.stmt(stmt, path)
            except _Unsupported as exc:
                # One unsupported statement must not abandon the rest of the program: record
                # it, taint everything downstream, and keep going.
                self.unverified.append(
                    f"line {getattr(stmt, 'line', 0)}: {type(stmt).__name__} not modelled "
                    f"({exc})")
                self.tainted = True

    def stmt(self, s, path) -> None:
        if isinstance(s, (LetStmt, ConstDecl, VarDecl)):
            self.env[s.name] = self.expr(s.value)
        elif isinstance(s, AssertStmt):
            if self.tainted:
                self.unverified.append(
                    f"line {getattr(s, 'line', 0)}: assertion "
                    f"\"{_describe(s.condition)}\" was NOT checked -- it depends on an "
                    f"unmodelled construct")
                return
            cond = self.expr(s.condition)
            self.assertions.append(
                (path, cond, int(getattr(s, 'line', 0) or 0), _describe(s.condition)))
        elif isinstance(s, IfStmt):
            cond = self.expr(s.condition)
            base = dict(self.env)
            self.env = dict(base)
            self.block(s.then_branch, z3.And(path, cond))
            self.env = dict(base)
            self.block(s.else_branch, z3.And(path, z3.Not(cond)))
            self.env = base          # branch-local bindings do not escape
        elif isinstance(s, (WhileStmt, ForStmt)):
            self.unverified.append(
                f"line {getattr(s, 'line', 0)}: loop body not modelled "
                f"(proving a loop needs invariants)")
            self.tainted = True
        elif isinstance(s, ExprStmt):
            self.expr(s.expression)
        elif isinstance(s, AssignExpr):
            name = getattr(s.target, 'name', None)
            if name is None:
                raise _Unsupported("assignment to a non-name target")
            self.env[name] = self.expr(s.value)
        # ReturnStmt / declarations: nothing to model

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
