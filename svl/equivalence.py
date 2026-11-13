"""SMT equivalence checking — does the refactored function still mean the same thing?

`svl.differential.DifferentialVerifier` compares *layer verdicts* between two versions, so
it detects drift from a pinned reference but cannot prove two functions equivalent: the
README itself notes that `a + 2`, `a - 2` and `a * 2` all pass every layer identically.

This module encodes two function bodies in Z3 and refutes `f(inputs) != g(inputs)`.  If the
negation is unsat, the functions are equivalent for every input the encoder models; if it is
sat, the model is a concrete counterexample.

Scope, deliberately narrow and reported honestly: straight-line bodies plus `if/else`
statements whose branches both return.  Recursion, loops, arrays, structs and calls to other
functions are declined (`unverified`) rather than modelled with the wrong semantics — the
same rule the SMT layer follows.  A false "proven" would be worse than no answer.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from svl.lexer import tokenize
from svl.parser_rd import (
    parse, Program, FuncDecl, LetStmt, ReturnStmt, IfStmt, ExprStmt, AssignExpr,
    Block, TypeExpr, Ident, NodeType,
)


class _Unsupported(Exception):
    pass


@dataclass
class EquivalenceResult:
    status: str                       # 'proven' | 'counterexample' | 'unverified' | 'signature-mismatch'
    counterexample: Optional[Dict[str, Any]] = None
    details: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when the functions are proven equivalent (a counterexample is a failure)."""
        return self.status == 'proven'


def _parse_function(source: str) -> FuncDecl:
    ast = parse(tokenize(source))
    for module in getattr(ast, 'modules', []):
        for stmt in module.body.statements:
            if isinstance(stmt, FuncDecl):
                return stmt
    for item in getattr(ast, 'items', []):
        if isinstance(item, FuncDecl):
            return item
    raise ValueError("no function declaration found")


def _type_str(ann: Optional[TypeExpr]) -> str:
    if ann is None:
        return 'void'
    kind = getattr(ann, 'kind', None)
    if kind == 'prim':
        return str(ann.value)
    if kind == 'struct':
        return f"struct {ann.value}"
    return str(getattr(ann, 'value', ann))


def _encode_body(verifier, func: FuncDecl, env: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
    """Encode a body, returning (return value or None, final env).

    Only straight-line statements and `if/else` with both branches returning are modelled.
    """
    env = dict(env)
    for stmt in func.body.statements:
        if isinstance(stmt, LetStmt):
            if stmt.value is None:
                raise _Unsupported("let without a value")
            env[stmt.name] = verifier._expr_in(stmt.value, env)
        elif isinstance(stmt, ReturnStmt):
            return (verifier._expr_in(stmt.value, env) if stmt.value is not None else None), env
        elif isinstance(stmt, IfStmt):
            cond = verifier._expr_in(stmt.condition, env)
            v_then, e_then = _encode_body(verifier, _as_func(stmt.then_branch), env)
            if stmt.else_branch is None:
                raise _Unsupported("if without else (the other branch returns nothing)")
            v_else, e_else = _encode_body(verifier, _as_func(stmt.else_branch), env)
            if v_then is None or v_else is None:
                raise _Unsupported("an if branch that does not return")
            merged = {}
            for key in set(e_then) | set(e_else):
                a, b = e_then.get(key), e_else.get(key)
                if a is None:
                    merged[key] = b
                elif b is None:
                    merged[key] = a
                else:
                    merged[key] = _z3_if(cond, a, b)
            return _z3_if(cond, v_then, v_else), merged
        elif isinstance(stmt, ExprStmt) and isinstance(stmt.expression, AssignExpr):
            assign = stmt.expression
            if not isinstance(assign.target, Ident):
                raise _Unsupported("assignment to a non-identifier")
            name = assign.target.name
            value = verifier._expr_in(assign.value, env)
            op = getattr(assign, 'operator', '=')
            if op != '=':
                raise _Unsupported(f"compound assignment '{op}' in an equivalence check")
            env[name] = value
        else:
            raise _Unsupported(f"{type(stmt).__name__} not modelled")
    return None, env


def _as_func(block: Block) -> FuncDecl:
    """Adapt a block to the `_encode_body` shape (it only reads `.body.statements`)."""
    return FuncDecl(type=NodeType.FUNC_DECL, line=0, column=0, offset=0,
                    name='<block>', params=[], return_type=None, body=block)


def _z3_if(cond, a, b):
    import z3
    return z3.If(cond, a, b)


def prove_equivalent(f_source: str, g_source: str,
                      timeout_ms: int = 5000) -> EquivalenceResult:
    """Prove (or refute) that two function declarations are equivalent."""
    try:
        import z3
    except ImportError:
        return EquivalenceResult('unverified', details=["z3-solver is not available"])

    try:
        f = _parse_function(f_source)
        g = _parse_function(g_source)
    except Exception as exc:                                      # noqa: BLE001
        return EquivalenceResult('unverified', details=[f"could not parse: {exc}"])

    f_params = [_type_str(p.type_ann) for p in f.params]
    g_params = [_type_str(p.type_ann) for p in g.params]
    if f_params != g_params or _type_str(f.return_type) != _type_str(g.return_type):
        return EquivalenceResult(
            'signature-mismatch',
            details=[f"f{f_params} -> {_type_str(f.return_type)} vs "
                     f"g{g_params} -> {_type_str(g.return_type)}"])

    from svl.smt_theorem import _SymbolicVerifier
    verifier = _SymbolicVerifier(timeout_ms=timeout_ms)

    try:
        env = {p.name: z3.Int(f"x_{p.name}") for p in f.params}
        out_f, _ = _encode_body(verifier, f, env)
        out_g, _ = _encode_body(verifier, g, {p.name: z3.Int(f"x_{p.name}") for p in g.params})
    except _Unsupported as exc:
        return EquivalenceResult('unverified', details=[str(exc)])
    except Exception as exc:                                      # noqa: BLE001
        return EquivalenceResult('unverified',
                                 details=[f"{type(exc).__name__}: {exc}"])

    if out_f is None or out_g is None:
        return EquivalenceResult('unverified', details=["a body does not return a value"])

    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    solver.add(out_f != out_g)
    result = solver.check()

    if result == z3.unsat:
        return EquivalenceResult('proven', details=[
            f"no input makes {f.name} differ from {g.name}"])
    if result == z3.sat:
        model = solver.model()
        counter = {}
        for p in f.params:
            try:
                value = model[z3.Int(f"x_{p.name}")]
                # A parameter the model leaves unconstrained can be ANY value; say so
                # rather than printing a misleading None.
                counter[p.name] = value.as_long() if value is not None else "any"
            except Exception:                                     # noqa: BLE001
                counter[p.name] = "any"
        return EquivalenceResult('counterexample', counterexample=counter, details=[
            f"{f.name}{counter} != {g.name}{counter}"])
    return EquivalenceResult('unverified', details=["the solver returned unknown"])


def svlc_diff(f_source: str, g_source: str) -> str:
    """A one-line human-readable verdict (used by the CLI)."""
    result = prove_equivalent(f_source, g_source)
    if result.status == 'proven':
        return "proven equivalent"
    if result.status == 'counterexample':
        return f"NOT equivalent: counterexample {result.counterexample}"
    if result.status == 'signature-mismatch':
        return "signature mismatch: " + "; ".join(result.details)
    return "unverified: " + "; ".join(result.details)
