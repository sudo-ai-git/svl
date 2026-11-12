#!/usr/bin/env python3
"""Spike 009: make the gate refuse constructs the backend silently mis-compiles.

F2 (iterator for), F5 (print <non-literal>), F6 (const reassign), F9 (try/catch), F10 (import).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402
from svl.lexer import tokenize, TokenType                     # noqa: E402
from svl.parser_rd import (parse, ForStmt, BinaryExpr, CallExpr, Literal,           # noqa: E402
                           AssignExpr, ExprStmt, TryStmt, IfStmt, WhileStmt,
                           ConstDecl, FuncDecl)
import svl.verify_gate as vg                                   # noqa: E402


def contract_problems(source):
    ast = parse(tokenize(source))
    problems = []
    consts = set()
    for m in ast.modules:
        for s in m.body.statements:
            if isinstance(s, ConstDecl):
                consts.add(s.name)

    def walk(stmts):
        for s in stmts:
            if isinstance(s, FuncDecl):
                walk(s.body.statements)
            elif isinstance(s, ForStmt):
                if not (isinstance(s.iter_expr, BinaryExpr) and s.iter_expr.operator == '..'):
                    problems.append("iterator for-loop is not supported by the backend")
                walk(s.body.statements)
            elif isinstance(s, IfStmt):
                walk(s.then_branch.statements)
                if s.else_branch is not None:
                    walk(s.else_branch.statements)
            elif isinstance(s, WhileStmt):
                walk(s.body.statements)
            elif isinstance(s, TryStmt):
                problems.append("try/catch is not supported by the backend")
                walk(s.try_block.statements)
                walk(s.catch_block.statements)
            elif isinstance(s, ExprStmt) and isinstance(s.expression, CallExpr):
                c = s.expression
                lit = (len(c.arguments) == 1 and isinstance(c.arguments[0], Literal)
                       and c.arguments[0].literal_type == 'string')
                if c.callee == 'print' and not lit:
                    problems.append("print(<non-string-literal>) is not supported by the backend")
            elif isinstance(s, ExprStmt) and isinstance(s.expression, AssignExpr):
                if getattr(s.expression.target, 'name', None) in consts:
                    problems.append("assignment to const is not supported by the backend")

    for m in ast.modules:
        walk(m.body.statements)
    # an IMPORT token that never became a top-level Import node is an inline import,
    # which the backend silently drops
    n_import_tokens = sum(1 for t in tokenize(source) if t.type == TokenType.IMPORT)
    if n_import_tokens > len(ast.imports):
        problems.append("import is not linked by the backend")
    return problems


_orig_verify = vg.verify_program


def patched_verify(source):
    probs = _orig_verify(source)
    try:
        probs.extend(contract_problems(source))
    except SyntaxError:
        pass
    return probs


CASES = {
    "for-in": ("module m { func main() type int { let a = [1,2,3] let s = 0"
               " for x in a { s += x } return s } }"),
    "print(int)": ("module m { func main() type void { let x = 5 print(x) return } }"),
    "const reassign": ("module m { const c: int = 5 func main() type int { c = 6 return c } }"),
    "try/catch": ("module m { func main() type int { try { let x = 1 }"
                  " catch e { let y = 2 } return 0 } }"),
    "import": ('module m { import "other" func main() type int { return 42 } }'),
}
VALID = ("module m { func main() type int { let a = [1,2,3] let s = 0"
         " for i in 0..3 { s += a[i] } return s } }")


def main():
    vg.verify_program = patched_verify
    try:
        refused = {}
        for name, src in CASES.items():
            try:
                vg.assert_verified(src)
                refused[name] = False
            except Exception:
                refused[name] = True
        valid_ok = True
        try:
            vg.assert_verified(VALID)
        except Exception:
            valid_ok = False
        ok = all(refused.values()) and valid_ok
        return verdict("009-gate-refuse-unsupported", ok,
                       f"refused={refused}, valid program still passes={valid_ok}")
    except Exception as exc:
        return verdict("009-gate-refuse-unsupported", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
