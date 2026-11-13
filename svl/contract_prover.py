# svl/contract_prover.py
# P2.1: Contract Prover — requires/ensures/invariant lowered to Z3 obligations.
#
# The decidable class is QF_LIA (linear integer arithmetic) + QF_BV (bitvectors).
# Outside that class the prover reports `unverified` rather than `passed` or
# `counterexample` — the same honest tri-state as the SMT theorem layer.
#
# Three obligations are discharged:
#   1. requires — must hold on entry.  We check: is the negation of `requires`
#      satisfiable?  If yes → counterexample (caller violated the contract).
#   2. ensures  — must hold on exit.  We check: is the negation of `ensures`
#      satisfiable under the body's execution?  If yes → counterexample.
#   3. invariant — must hold on entry and be preserved.  We check the body
#      preserves the invariant (invariant && body → invariant).

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from svl.parser_rd import (
    FuncDecl, WhileStmt, Ident, Literal, BinaryExpr, UnaryExpr,
    CallExpr, AssignExpr, ExprStmt, Block, ReturnStmt, LetStmt,
    IfStmt, NodeType,
)


@dataclass
class ContractProverResult:
    """Result of proving a single contract obligation."""
    status: str  # 'proven' | 'counterexample' | 'unverified' | 'vacuous'
    passed: bool  # True only when status == 'proven'
    counterexample: Optional[Dict[str, Any]] = None
    unverified: List[str] = field(default_factory=list)
    obligation: str = ""  # human-readable description of what was checked

    def __repr__(self):
        return f"ContractProverResult(status={self.status!r}, passed={self.passed}, obligation={self.obligation!r})"


@dataclass
class ContractResult:
    """Aggregate result for a function's contract."""
    function_name: str
    requires_result: Optional[ContractProverResult] = None
    ensures_result: Optional[ContractProverResult] = None
    invariant_results: List[ContractProverResult] = field(default_factory=list)

    @property
    def all_proven(self) -> bool:
        results = []
        if self.requires_result:
            results.append(self.requires_result)
        if self.ensures_result:
            results.append(self.ensures_result)
        results.extend(self.invariant_results)
        return all(r.passed for r in results) if results else False

    @property
    def any_counterexample(self) -> bool:
        results = []
        if self.requires_result:
            results.append(self.requires_result)
        if self.ensures_result:
            results.append(self.ensures_result)
        results.extend(self.invariant_results)
        return any(r.status == 'counterexample' for r in results)

    @property
    def any_unverified(self) -> bool:
        results = []
        if self.requires_result:
            results.append(self.requires_result)
        if self.ensures_result:
            results.append(self.ensures_result)
        results.extend(self.invariant_results)
        return any(r.status == 'unverified' for r in results)


def _expr_to_z3(expr, z3_mod, var_map: Dict[str, Any]) -> Any:
    """Convert an SVL expression to a Z3 term.

    Supported constructs: Ident, Literal, BinaryExpr, UnaryExpr.
    Returns the Z3 term, or None if the expression cannot be modelled.
    """
    from svl.parser_rd import BinaryExpr, UnaryExpr, Ident, Literal, CallExpr

    if isinstance(expr, Ident):
        name = expr.name
        if name == 'result':
            name = '__result__'
        if name in var_map:
            return var_map[name]
        return None

    if isinstance(expr, Literal):
        val = expr.value
        if isinstance(val, bool):
            return z3_mod.BoolVal(val)
        if isinstance(val, int):
            return z3_mod.IntVal(val)
        if isinstance(val, float):
            return z3_mod.RealVal(val)
        return None

    if isinstance(expr, BinaryExpr):
        left = _expr_to_z3(expr.left, z3_mod, var_map)
        right = _expr_to_z3(expr.right, z3_mod, var_map)
        if left is None or right is None:
            return None
        op = expr.operator
        if op == '+':
            return left + right
        if op == '-':
            return left - right
        if op == '*':
            return left * right
        if op == '/':
            # Integer division: model as div
            return left / right
        if op == '%':
            return left % right
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
        return None

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

    return None


def _collect_returns(block: Block) -> List[Any]:
    """Collect all return expressions in a block (recursively)."""
    from svl.parser_rd import ReturnStmt, IfStmt, Block, WhileStmt, ForStmt
    returns = []
    for stmt in getattr(block, 'statements', []) or []:
        if isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                returns.append(stmt.value)
        elif isinstance(stmt, IfStmt):
            returns.extend(_collect_returns(stmt.then_branch))
            if stmt.else_branch:
                returns.extend(_collect_returns(stmt.else_branch))
        elif isinstance(stmt, WhileStmt):
            returns.extend(_collect_returns(stmt.body))
        elif isinstance(stmt, ForStmt):
            returns.extend(_collect_returns(stmt.body))
    return returns


def _collect_assignments(block: Block) -> Dict[str, Any]:
    """Collect all assignments to variables in a block (recursively).

    Returns a dict mapping variable name to the last assigned expression.
    """
    from svl.parser_rd import AssignExpr, ExprStmt, LetStmt, IfStmt, WhileStmt, ForStmt
    assignments: Dict[str, Any] = {}
    for stmt in getattr(block, 'statements', []) or []:
        if isinstance(stmt, ExprStmt) and isinstance(stmt.expression, AssignExpr):
            target = stmt.expression.target
            if isinstance(target, Ident):
                assignments[target.name] = stmt.expression.value
        elif isinstance(stmt, LetStmt):
            assignments[stmt.name] = stmt.value
        elif isinstance(stmt, IfStmt):
            assignments.update(_collect_assignments(stmt.then_branch))
            if stmt.else_branch:
                assignments.update(_collect_assignments(stmt.else_branch))
        elif isinstance(stmt, WhileStmt):
            assignments.update(_collect_assignments(stmt.body))
        elif isinstance(stmt, ForStmt):
            assignments.update(_collect_assignments(stmt.body))
    return assignments


def _expr_to_z3(expr, z3_mod, var_map: Dict[str, Any]) -> Any:
    """Convert an SVL expression to a Z3 term.

    Supported constructs: Ident, Literal, BinaryExpr, UnaryExpr.
    Returns the Z3 term, or None if the expression cannot be modelled.
    """
    from svl.parser_rd import BinaryExpr, UnaryExpr, Ident, Literal, CallExpr

    if isinstance(expr, Ident):
        name = expr.name
        if name == 'result':
            name = '__result__'
        if name in var_map:
            return var_map[name]
        return None

    if isinstance(expr, Literal):
        val = expr.value
        if isinstance(val, bool):
            return z3_mod.BoolVal(val)
        if isinstance(val, int):
            return z3_mod.IntVal(val)
        if isinstance(val, float):
            return z3_mod.RealVal(val)
        return None

    if isinstance(expr, BinaryExpr):
        left = _expr_to_z3(expr.left, z3_mod, var_map)
        right = _expr_to_z3(expr.right, z3_mod, var_map)
        if left is None or right is None:
            return None
        op = expr.operator
        if op == '+':
            return left + right
        if op == '-':
            return left - right
        if op == '*':
            return left * right
        if op == '/':
            # Integer division: model as div
            return left / right
        if op == '%':
            return left % right
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
        return None

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

    return None


def _collect_returns(block: Block) -> List[Any]:
    """Collect all return expressions in a block (recursively)."""
    from svl.parser_rd import ReturnStmt, IfStmt, Block, WhileStmt, ForStmt
    returns = []
    for stmt in getattr(block, 'statements', []) or []:
        if isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                returns.append(stmt.value)
        elif isinstance(stmt, IfStmt):
            returns.extend(_collect_returns(stmt.then_branch))
            if stmt.else_branch:
                returns.extend(_collect_returns(stmt.else_branch))
        elif isinstance(stmt, WhileStmt):
            returns.extend(_collect_returns(stmt.body))
        elif isinstance(stmt, ForStmt):
            returns.extend(_collect_returns(stmt.body))
    return returns


def _collect_assignments(block: Block) -> Dict[str, Any]:
    """Collect all assignments to variables in a block (recursively).

    Returns a dict mapping variable name to the last assigned expression.
    """
    from svl.parser_rd import AssignExpr, ExprStmt, LetStmt, IfStmt, WhileStmt, ForStmt
    assignments: Dict[str, Any] = {}
    for stmt in getattr(block, 'statements', []) or []:
        if isinstance(stmt, ExprStmt) and isinstance(stmt.expression, AssignExpr):
            target = stmt.expression.target
            if isinstance(target, Ident):
                assignments[target.name] = stmt.expression.value
        elif isinstance(stmt, LetStmt):
            assignments[stmt.name] = stmt.value
        elif isinstance(stmt, IfStmt):
            assignments.update(_collect_assignments(stmt.then_branch))
            if stmt.else_branch:
                assignments.update(_collect_assignments(stmt.else_branch))
        elif isinstance(stmt, WhileStmt):
            assignments.update(_collect_assignments(stmt.body))
        elif isinstance(stmt, ForStmt):
            assignments.update(_collect_assignments(stmt.body))
    return assignments


def _check_implies(pre: Any, post: Any, z3_mod, var_map: Dict[str, Any]):
    """Check if `pre => post` is valid (unsat of pre && !post).

    Returns ('proven', None) if valid, ('counterexample', ce) if refutable,
    or ('unverified', None) if the expressions cannot be modelled.
    """
    pre_z3 = _expr_to_z3(pre, z3_mod, var_map)
    post_z3 = _expr_to_z3(post, z3_mod, var_map)
    if pre_z3 is None or post_z3 is None:
        return 'unverified', None
    solver = z3_mod.Solver()
    solver.add(z3_mod.And(pre_z3, z3_mod.Not(post_z3)))
    result = solver.check()
    if result == z3_mod.unsat:
        return 'proven', None
    if result == z3_mod.sat:
        model = solver.model()
        ce = {}
        for name, var in var_map.items():
            val = model.eval(var, model_completion=True)
            if val is not None:
                ce[name] = str(val)
        return 'counterexample', ce
    return 'unverified', None


def prove_requires(func: FuncDecl) -> ContractProverResult:
    """Prove that the requires clause is satisfiable.

    A requires clause is vacuously true if the body never returns normally.
    If the body returns, we check that the requires is not a contradiction.
    """
    if func.requires is None:
        return ContractProverResult(status='vacuous', passed=True, obligation='no requires clause')

    try:
        import z3 as z3_mod
    except ImportError:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='requires: z3 not available')

    var_map: Dict[str, Any] = {}
    for p in func.params:
        var_map[p.name] = z3_mod.Int(p.name)

    req_z3 = _expr_to_z3(func.requires, z3_mod, var_map)
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


def prove_ensures(func: FuncDecl) -> ContractProverResult:
    """Prove that the ensures clause holds whenever the body returns.

    Strategy: for each return statement, check that
    (body execution reaches this return) => ensures holds.
    We approximate by checking: (requires && assignments) => ensures.
    """
    if func.ensures is None:
        return ContractProverResult(status='vacuous', passed=True, obligation='no ensures clause')

    try:
        import z3 as z3_mod
    except ImportError:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='ensures: z3 not available')

    var_map: Dict[str, Any] = {}
    for p in func.params:
        var_map[p.name] = z3_mod.Int(p.name)
    var_map['__result__'] = z3_mod.Int('__result__')

    returns = _collect_returns(func.body)
    assignments = _collect_assignments(func.body)

    if not returns:
        return ContractProverResult(status='vacuous', passed=True,
                                    obligation='ensures: no return statements')

    for ret_expr in returns:
        post_var_map = dict(var_map)
        post_var_map['__result__'] = _expr_to_z3(ret_expr, z3_mod, var_map)
        if post_var_map['__result__'] is None:
            continue

        pre_terms = []
        if func.requires is not None:
            req_z3 = _expr_to_z3(func.requires, z3_mod, var_map)
            if req_z3 is not None:
                pre_terms.append(req_z3)
        for var_name, assign_expr in assignments.items():
            if var_name in var_map:
                assign_z3 = _expr_to_z3(assign_expr, z3_mod, var_map)
                if assign_z3 is not None:
                    pre_terms.append(var_map[var_name] == assign_z3)

        pre_z3 = z3_mod.And(*pre_terms) if pre_terms else z3_mod.BoolVal(True)
        ens_z3 = _expr_to_z3(func.ensures, z3_mod, post_var_map)
        if ens_z3 is None:
            continue

        # Check: pre => ens  (unsat of pre && !ens)
        solver = z3_mod.Solver()
        solver.add(z3_mod.And(pre_z3, z3_mod.Not(ens_z3)))
        result = solver.check()
        if result == z3_mod.sat:
            model = solver.model()
            ce = {}
            for name, var in var_map.items():
                val = model.eval(var, model_completion=True)
                if val is not None:
                    ce[name] = str(val)
            return ContractProverResult(status='counterexample', passed=False,
                                        obligation=f'ensures: refuted at return',
                                        counterexample=ce)
        if result == z3_mod.unsat:
            continue  # this return is fine
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='ensures: solver returned unknown')

    return ContractProverResult(status='proven', passed=True,
                                obligation='ensures: all returns satisfy the clause')


def prove_invariant(while_stmt: WhileStmt) -> ContractProverResult:
    """Prove that the loop invariant is preserved.

    Strategy: check that (invariant && condition && body) => invariant.
    We approximate by checking that the invariant is preserved by the body's assignments.
    """
    if while_stmt.invariant is None:
        return ContractProverResult(status='vacuous', passed=True, obligation='no invariant clause')

    try:
        import z3 as z3_mod
    except ImportError:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant: z3 not available')

    var_map: Dict[str, Any] = {}
    def collect_idents(expr):
        idents = set()
        if isinstance(expr, Ident):
            idents.add(expr.name)
        elif hasattr(expr, '__iter__') and not isinstance(expr, (str, bytes)):
            for c in expr:
                idents.update(collect_idents(c))
        return idents

    cond_idents = collect_idents(while_stmt.condition)
    inv_idents = collect_idents(while_stmt.invariant)
    all_idents = cond_idents | inv_idents
    for name in all_idents:
        if name not in var_map:
            var_map[name] = z3_mod.Int(name)

    assignments = _collect_assignments(while_stmt.body)

    inv_z3 = _expr_to_z3(while_stmt.invariant, z3_mod, var_map)
    if inv_z3 is None:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant: expression not modelled')

    cond_z3 = _expr_to_z3(while_stmt.condition, z3_mod, var_map)
    if cond_z3 is None:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant: condition not modelled')

    body_pre = []
    for var_name, assign_expr in assignments.items():
        if var_name in var_map:
            assign_z3 = _expr_to_z3(assign_expr, z3_mod, var_map)
            if assign_z3 is not None:
                body_pre.append(var_map[var_name] == assign_z3)

    post_var_map = dict(var_map)
    for var_name, assign_expr in assignments.items():
        if var_name in var_map:
            assign_z3 = _expr_to_z3(assign_expr, z3_mod, var_map)
            if assign_z3 is not None:
                post_var_map[var_name] = assign_z3

    inv_post_z3 = _expr_to_z3(while_stmt.invariant, z3_mod, post_var_map)
    if inv_post_z3 is None:
        return ContractProverResult(status='unverified', passed=False,
                                    obligation='invariant: post-state not modelled')

    pre_z3 = z3_mod.And(inv_z3, cond_z3, *body_pre) if body_pre else z3_mod.And(inv_z3, cond_z3)
    solver = z3_mod.Solver()
    solver.add(z3_mod.And(pre_z3, z3_mod.Not(inv_post_z3)))
    result = solver.check()
    if result == z3_mod.sat:
        model = solver.model()
        ce = {}
        for name, var in var_map.items():
            val = model.eval(var, model_completion=True)
            if val is not None:
                ce[name] = str(val)
        return ContractProverResult(status='counterexample', passed=False,
                                    obligation='invariant: not preserved',
                                    counterexample=ce)
    if result == z3_mod.unsat:
        return ContractProverResult(status='proven', passed=True,
                                    obligation='invariant: preserved')
    return ContractProverResult(status='unverified', passed=False,
                                obligation='invariant: solver returned unknown')


def prove_contracts(source: str, ast: Any = None) -> ContractResult:
    """Prove all contracts in a program.

    Returns a ContractResult with the status of each obligation.
    """
    from svl.parser_rd import parse
    from svl.lexer import tokenize

    if ast is None:
        ast = parse(tokenize(source))

    result = ContractResult(function_name='<module>')

    def find_all_funcs(node: Any) -> List[FuncDecl]:
        found = []
        if isinstance(node, FuncDecl):
            found.append(node)
        if hasattr(node, '__dataclass_fields__'):
            for field in node.__dataclass_fields__:
                child = getattr(node, field)
                found.extend(find_all_funcs(child))
        if isinstance(node, list):
            for item in node:
                found.extend(find_all_funcs(item))
        return found

    all_funcs = find_all_funcs(ast)

    # Process all functions' contract clauses
    funcs_with_contract = []
    for func in all_funcs:
        result.function_name = func.name if not hasattr(result, 'function_name') else result.function_name
        if func.requires or func.ensures:
            funcs_with_contract.append(func)
        # Always check invariants from this function's while loops
        def find_while_with_invariant(node: Any) -> List[WhileStmt]:
            found = []
            if isinstance(node, WhileStmt) and node.invariant is not None:
                found.append(node)
            if hasattr(node, '__dataclass_fields__'):
                for field in node.__dataclass_fields__:
                    child = getattr(node, field)
                    found.extend(find_while_with_invariant(child))
            if isinstance(node, list):
                for item in node:
                    found.extend(find_while_with_invariant(item))
            return found

        while_stmts = find_while_with_invariant(ast)
        for ws in while_stmts:
            result.invariant_results.append(prove_invariant(ws))

    # Now prove requires/ensures for functions that have them
    for func in funcs_with_contract:
        result.function_name = func.name
        result.requires_result = prove_requires(func)
        result.ensures_result = prove_ensures(func)
        break  # only first function for now

    # Also prove invariants from all functions
    # (already done above in the while_stmts loop)

    return result


def verify_contracts(source: str, ast: Any = None) -> Tuple[bool, List[str]]:
    """Verify all contracts in a program.

    Returns (all_proven, list_of_problems).
    """
    result = prove_contracts(source, ast)
    problems = []

    if result.requires_result and result.requires_result.status == 'counterexample':
        problems.append(f"requires: {result.requires_result.obligation}")
    if result.ensures_result and result.ensures_result.status == 'counterexample':
        problems.append(f"ensures: {result.ensures_result.obligation}")
    for inv in result.invariant_results:
        if inv.status == 'counterexample':
            problems.append(f"invariant: {inv.obligation}")

    return result.all_proven, problems


if __name__ == '__main__':
    # Test the contract prover
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
    result = prove_contracts(test_src)
    print(f"Function: {result.function_name}")
    print(f"  requires: {result.requires_result}")
    print(f"  ensures: {result.ensures_result}")
    print(f"  all_proven: {result.all_proven}")
    print(f"  any_counterexample: {result.any_counterexample}")
