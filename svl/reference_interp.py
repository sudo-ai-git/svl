"""Reference interpreter for the SVL core — an independent oracle for the WASM backend.

The compiler is the de-facto specification: until now nothing checked that the emitted
WASM matches what the source says.  This module is a small tree-walking evaluator over
the `parser_rd` AST for the supported subset, and `svl.differential_exec` runs a program
through BOTH the interpreter and wasmtime and compares the results.

Scope (the subset the backend actually runs): int/float/bool/string literals, arithmetic
and comparison, `let`/assignment, `if`/`else`, `while`, `for i in a..b`, `for x in <array>`,
arrays (`a[i]`, `len`, `zeros`), structs (literals, field read/write), `match`, function
calls and recursion, `return`, `assert`, `print`/`print_int`, `const`/`var` globals,
`try`/`catch`/`throw`, `if..then..else` expressions, and `await` (the host import is the
identity).  Lambdas and `extern` host calls are out of scope.

Semantics are matched to WASM, not to Python: `+ - *` wrap at 32 bits, `/` truncates toward
zero and `%` takes the sign of the dividend, and bitwise ops act on 32-bit values.
"""
from typing import Any, Dict, List, Optional, Tuple

from svl.lexer import tokenize
from svl.parser_rd import (
    parse, Program, Module, FuncDecl, StructDecl, ConstDecl, VarDecl, Block,
    LetStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt, AssertStmt, TryStmt, ThrowStmt,
    ExprStmt, BinaryExpr, UnaryExpr, CallExpr, MatchExpr, AwaitExpr, LambdaExpr,
    StructLit, ArrayLit, Ident, Literal, CaseClause, TernaryExpr, AssignExpr,
    IndexExpr, FieldAccess, ExternDecl, NodeType,
)


class ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


class ThrowSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


class AssertSignal(Exception):
    pass


class Env:
    """A lexical scope.  Assignment walks up the chain; new names stay local."""

    def __init__(self, parent: Optional['Env'] = None):
        self.bindings: Dict[str, Any] = {}
        self.parent = parent

    def lookup(self, name: str) -> Any:
        env: Optional[Env] = self
        while env is not None:
            if name in env.bindings:
                return env.bindings[name]
            env = env.parent
        raise KeyError(name)

    def assign(self, name: str, value: Any) -> None:
        env: Optional[Env] = self
        while env is not None:
            if name in env.bindings:
                env.bindings[name] = value
                return
            env = env.parent
        self.bindings[name] = value

    def define(self, name: str, value: Any) -> None:
        self.bindings[name] = value


def _wrap32(v: int) -> int:
    """WASM i32 arithmetic wraps; Python ints do not."""
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def _trunc_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _trunc_rem(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a - _trunc_div(a, b) * b


class ReferenceInterpreter:
    """Tree-walking evaluator over the AST."""

    def __init__(self) -> None:
        self.functions: Dict[str, FuncDecl] = {}
        self.structs: Dict[str, List[str]] = {}
        self.globals: Dict[str, Any] = {}
        self.consts: set = set()
        self.output: List[str] = []
        # Functions are not closures: a call's parent scope is the GLOBAL scope.
        self.global_env: Env = Env()

    # -- setup --------------------------------------------------------------

    def run(self, source: str) -> Tuple[Any, str]:
        """Execute the program's `main` and return (return value, printed output)."""
        ast = parse(tokenize(source))
        self._collect(ast)
        main = self._find_main(ast)
        for name, value in self.globals.items():
            self.global_env.define(name, value)
        try:
            value = self._call_function(main, [], self.global_env)
        except ReturnSignal as ret:
            value = ret.value
        return value, ''.join(self.output)

    def _collect(self, ast: Program) -> None:
        for item in getattr(ast, 'items', []):
            self._collect_item(item, self.globals)
        for module in getattr(ast, 'modules', []):
            for stmt in module.body.statements:
                self._collect_item(stmt, self.globals)

    def _collect_item(self, item: Any, env: Dict[str, Any]) -> None:
        if isinstance(item, FuncDecl):
            self.functions[item.name] = item
        elif isinstance(item, StructDecl):
            self.structs[item.name] = [f.name for f in item.fields]
        elif isinstance(item, (ConstDecl, VarDecl)):
            value = self._eval(item.value, Env())
            env[item.name] = value
            if isinstance(item, ConstDecl):
                self.consts.add(item.name)

    def _find_main(self, ast: Program) -> FuncDecl:
        for module in getattr(ast, 'modules', []):
            for stmt in module.body.statements:
                if isinstance(stmt, FuncDecl) and stmt.name == 'main':
                    return stmt
        if 'main' in self.functions:
            return self.functions['main']
        raise ValueError("no `main` function found")

    # -- statements ---------------------------------------------------------

    def _exec_block(self, block: Block, env: Env) -> None:
        for stmt in block.statements:
            self._exec(stmt, env)

    def _exec(self, stmt: Any, env: Env) -> None:
        if isinstance(stmt, LetStmt):
            env.define(stmt.name, self._eval(stmt.value, env))
        elif isinstance(stmt, ConstDecl):
            env.define(stmt.name, self._eval(stmt.value, env))
            self.consts.add(stmt.name)
        elif isinstance(stmt, VarDecl):
            env.define(stmt.name, self._eval(stmt.value, env))
        elif isinstance(stmt, ExprStmt):
            self._exec_expr_stmt(stmt.expression, env)
        elif isinstance(stmt, IfStmt):
            if self._truth(self._eval(stmt.condition, env)):
                self._exec_block(stmt.then_branch, Env(env))
            elif stmt.else_branch is not None:
                self._exec_block(stmt.else_branch, Env(env))
        elif isinstance(stmt, WhileStmt):
            while self._truth(self._eval(stmt.condition, env)):
                self._exec_block(stmt.body, Env(env))
        elif isinstance(stmt, ForStmt):
            self._exec_for(stmt, env)
        elif isinstance(stmt, ReturnStmt):
            raise ReturnSignal(self._eval(stmt.value, env) if stmt.value is not None else None)
        elif isinstance(stmt, AssertStmt):
            if not self._truth(self._eval(stmt.condition, env)):
                raise AssertSignal("assertion failed")
        elif isinstance(stmt, ThrowStmt):
            raise ThrowSignal(self._eval(stmt.value, env))
        elif isinstance(stmt, TryStmt):
            try:
                self._exec_block(stmt.try_block, Env(env))
            except ThrowSignal as thrown:
                catch_env = Env(env)
                catch_env.define(stmt.catch_var, thrown.value)
                self._exec_block(stmt.catch_block, catch_env)
        elif isinstance(stmt, FuncDecl):
            self.functions[stmt.name] = stmt
        else:
            raise NotImplementedError(f"reference interpreter: statement {type(stmt).__name__}")

    def _exec_expr_stmt(self, expr: Any, env: Env) -> None:
        if isinstance(expr, AssignExpr):
            self._exec_assign(expr, env)
        else:
            self._eval(expr, env)

    def _exec_assign(self, expr: AssignExpr, env: Env) -> None:
        value = self._eval(expr.value, env)
        target = expr.target
        op = getattr(expr, 'operator', '=')
        if isinstance(target, Ident):
            if target.name in self.consts:
                raise AssertionError(f"assignment to const '{target.name}'")
            current = env.lookup(target.name)
            env.assign(target.name, self._apply(op, current, value))
        elif isinstance(target, (IndexExpr, BinaryExpr)):
            base, index = self._resolve_location(target, env)
            current = base[index + 1]
            base[index + 1] = self._apply(op, current, value)
        elif isinstance(target, FieldAccess):
            struct, field = self._resolve_field(target, env)
            current = struct[field]
            struct[field] = self._apply(op, current, value)
        else:
            raise NotImplementedError(
                f"reference interpreter: assignment target {type(target).__name__}")

    def _apply(self, op: str, left: Any, right: Any) -> Any:
        if op == '=':
            return right
        return self._binary(op[0], left, right)

    def _exec_for(self, stmt: ForStmt, env: Env) -> None:
        iterable = stmt.iter_expr
        if isinstance(iterable, BinaryExpr) and iterable.operator == '..':
            start = self._eval(iterable.left, env)
            end = self._eval(iterable.right, env)
            seq = list(range(start, end))
        else:
            seq = self._iterable(self._eval(iterable, env))
        for item in seq:
            loop_env = Env(env)
            loop_env.define(stmt.var, item)
            self._exec_block(stmt.body, loop_env)

    def _iterable(self, value: Any) -> List[Any]:
        if isinstance(value, list):
            return value[1:value[0] + 1]
        raise TypeError(f"not iterable: {value!r}")

    # -- expressions --------------------------------------------------------

    def _eval(self, expr: Any, env: Env) -> Any:
        if expr is None:
            return None
        if isinstance(expr, Literal):
            return expr.value
        if isinstance(expr, Ident):
            return self._lookup(expr.name, env)
        if isinstance(expr, BinaryExpr):
            return self._eval_binary(expr, env)
        if isinstance(expr, IndexExpr):
            base, index = self._resolve_location(expr, env)
            return base[index + 1]
        if isinstance(expr, FieldAccess):
            struct, field = self._resolve_field(expr, env)
            return struct[field]
        if isinstance(expr, UnaryExpr):
            return self._eval_unary(expr, env)
        if isinstance(expr, TernaryExpr):
            return (self._eval(expr.then_expr, env) if self._truth(self._eval(expr.condition, env))
                    else self._eval(expr.else_expr, env))
        if isinstance(expr, CallExpr):
            return self._eval_call(expr, env)
        if isinstance(expr, ArrayLit):
            elements = [self._eval(e, env) for e in expr.elements]
            return [len(elements)] + elements
        if isinstance(expr, StructLit):
            return {f.name: self._eval(f.value, env) for f in expr.fields}
        if isinstance(expr, MatchExpr):
            return self._eval_match(expr, env)
        if isinstance(expr, AwaitExpr):
            return self._eval(expr.expression, env)
        if isinstance(expr, LambdaExpr):
            raise NotImplementedError("reference interpreter: lambdas are out of scope")
        raise NotImplementedError(
            f"reference interpreter: expression {type(expr).__name__}")

    def _lookup(self, name: str, env: Env) -> Any:
        try:
            return env.lookup(name)
        except KeyError:
            pass
        if name in self.globals:
            return self.globals[name]
        raise KeyError(f"unknown identifier '{name}'")

    def _eval_binary(self, expr: BinaryExpr, env: Env) -> Any:
        op = expr.operator
        if op == '.':
            struct, field = self._resolve_field(expr, env)
            return struct[field]
        if op == '[]':
            base, index = self._resolve_location(expr, env)
            return base[index + 1]
        if op == '&&':
            return self._truth(self._eval(expr.left, env)) and self._truth(self._eval(expr.right, env))
        if op == '||':
            return self._truth(self._eval(expr.left, env)) or self._truth(self._eval(expr.right, env))
        left = self._eval(expr.left, env)
        right = self._eval(expr.right, env)
        return self._binary(op, left, right)

    def _binary(self, op: str, left: Any, right: Any) -> Any:
        if op == '+':
            if isinstance(left, str) or isinstance(right, str):
                return f"{left}{right}"
            return _wrap32(left + right) if isinstance(left, int) and isinstance(right, int) else left + right
        if op == '-':
            return _wrap32(left - right) if isinstance(left, int) and isinstance(right, int) else left - right
        if op == '*':
            return _wrap32(left * right) if isinstance(left, int) and isinstance(right, int) else left * right
        if op == '/':
            return _trunc_div(left, right) if isinstance(left, int) and isinstance(right, int) else left / right
        if op == '%':
            return _trunc_rem(left, right)
        if op in ('==', '!=', '<', '>', '<=', '>='):
            return {
                '==': left == right, '!=': left != right, '<': left < right,
                '>': left > right, '<=': left <= right, '>=': left >= right,
            }[op]
        if op == '&':
            return _wrap32(int(left) & int(right))
        if op == '|':
            return _wrap32(int(left) | int(right))
        if op == '^':
            return _wrap32(int(left) ^ int(right))
        if op == '<<':
            return _wrap32(int(left) << int(right))
        if op == '>>':
            return _wrap32(int(left) >> int(right))
        raise NotImplementedError(f"reference interpreter: operator {op!r}")

    def _eval_unary(self, expr: UnaryExpr, env: Env) -> Any:
        value = self._eval(expr.operand, env)
        if expr.operator == '-':
            return _wrap32(-value) if isinstance(value, int) else -value
        if expr.operator == '!':
            return not self._truth(value)
        if expr.operator == '~':
            return _wrap32(~int(value))
        raise NotImplementedError(f"reference interpreter: unary {expr.operator!r}")

    def _eval_call(self, expr: CallExpr, env: Env) -> Any:
        name = expr.callee
        args = [self._eval(a, env) for a in expr.arguments]
        if name == 'print':
            self.output.append('' if args[0] is None else str(args[0]))
            return None
        if name == 'print_int':
            self.output.append(str(int(args[0])))
            return None
        if name == 'len':
            return args[0][0] if isinstance(args[0], list) else len(args[0])
        if name == 'zeros':
            n = int(args[0])
            return [n] + [0] * n
        if name in self.functions:
            return self._call_function(self.functions[name], args, env)
        raise KeyError(f"unknown function '{name}'")

    def _call_function(self, func: FuncDecl, args: List[Any], env: Env) -> Any:
        call_env = Env(self.global_env)
        for param, value in zip(func.params, args):
            call_env.define(param.name, value)
        try:
            self._exec_block(func.body, call_env)
        except ReturnSignal as ret:
            return ret.value
        return None

    def _eval_match(self, expr: MatchExpr, env: Env) -> Any:
        subject = self._eval(expr.subject, env)
        for case in expr.cases:
            if self._pattern_matches(case.pattern, subject, env):
                case_env = Env(env)
                if getattr(case.pattern, 'kind', None) == 'ident':
                    case_env.define(case.pattern.value, subject)
                return self._eval(case.body, case_env)
        raise AssertionError("non-exhaustive match")

    def _pattern_matches(self, pattern: Any, subject: Any, env: Env) -> bool:
        kind = getattr(pattern, 'kind', None)
        if kind == 'wildcard':
            return True
        if kind == 'ident':
            return True
        if kind == 'int':
            return subject == pattern.value
        if kind == 'bool':
            return subject == pattern.value
        if kind == 'string':
            return subject == pattern.value
        if kind == 'null':
            return subject is None
        return False

    def _resolve_location(self, expr: Any, env: Env) -> Tuple[List[Any], int]:
        if isinstance(expr, IndexExpr):
            base = self._eval(expr.left, env)
            index = self._eval(expr.right, env)
        else:                                   # BinaryExpr('[]', base, index)
            base = self._eval(expr.left, env)
            index = self._eval(expr.right, env)
        return base, index

    def _resolve_field(self, expr: Any, env: Env) -> Tuple[Dict[str, Any], str]:
        if isinstance(expr, FieldAccess):
            struct = self._eval(expr.left, env)
            field = expr.right.name if isinstance(expr.right, Ident) else str(expr.right)
        else:                                   # BinaryExpr('.', base, field)
            struct = self._eval(expr.left, env)
            field = expr.right.name if isinstance(expr.right, Ident) else str(expr.right)
        return struct, field

    @staticmethod
    def _truth(value: Any) -> bool:
        return bool(value)


def interpret(source: str) -> Tuple[Any, str]:
    """Convenience: run a program through the reference interpreter."""
    return ReferenceInterpreter().run(source)
