#!/usr/bin/env python3
"""Spike 001: does scope-aware alpha-renaming fix F1 (inner let clobbers outer)?"""
import dataclasses
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))          # harness.py
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import run_wat, verdict, parse_src                      # noqa: E402
from svl.parser_rd import (                                          # noqa: E402
    ASTNode, Program, Module, Block, LetStmt, IfStmt, WhileStmt, ForStmt,
    ReturnStmt, AssertStmt, ExprStmt, TryStmt, ConstDecl, VarDecl,
    FuncDecl, Ident, FieldAccess, IndexExpr,
)
from svl.compiler_wasm import compile_to_wasm                        # noqa: E402


class Renamer:
    def __init__(self):
        self.n = 0
        self.scopes = []

    def fresh(self, name):
        self.n += 1
        return f"{name}__v{self.n}"

    def push(self):
        self.scopes.append({})

    def pop(self):
        self.scopes.pop()

    def bind(self, name):
        new = self.fresh(name)
        self.scopes[-1][name] = new
        return new

    def resolve(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return name

    # ---- statements ----
    def stmts(self, stmts):
        for s in stmts:
            self.stmt(s)

    def stmt(self, s):
        if isinstance(s, LetStmt):
            self.expr(s.value)
            s.name = self.bind(s.name)
        elif isinstance(s, IfStmt):
            self.expr(s.condition)
            self.push(); self.stmts(s.then_branch.statements); self.pop()
            if s.else_branch is not None:
                self.push(); self.stmts(s.else_branch.statements); self.pop()
        elif isinstance(s, WhileStmt):
            self.expr(s.condition)
            self.push(); self.stmts(s.body.statements); self.pop()
        elif isinstance(s, ForStmt):
            self.expr(s.iter_expr)
            self.push()
            s.var = self.bind(s.var)
            self.stmts(s.body.statements)
            self.pop()
        elif isinstance(s, ReturnStmt):
            if s.value is not None:
                self.expr(s.value)
        elif isinstance(s, AssertStmt):
            self.expr(s.condition)
        elif isinstance(s, ExprStmt):
            self.expr(s.expression)
        elif isinstance(s, Block):
            self.push(); self.stmts(s.statements); self.pop()
        elif isinstance(s, TryStmt):
            self.push(); self.stmts(s.try_block.statements); self.pop()
            self.push()
            s.catch_var = self.bind(s.catch_var)
            self.stmts(s.catch_block.statements)
            self.pop()
        elif isinstance(s, (ConstDecl, VarDecl)):
            self.expr(s.value)
            s.name = self.bind(s.name)
        elif isinstance(s, FuncDecl):
            self.push()
            for p in s.params:
                p.name = self.bind(p.name)
            self.stmts(s.body.statements)
            self.pop()

    # ---- expressions ----
    def expr(self, e):
        if e is None or isinstance(e, (str, int, float, bool)):
            return
        if isinstance(e, Ident):
            e.name = self.resolve(e.name)
            return
        if isinstance(e, FieldAccess):
            self.expr(e.left)
            return                              # e.right is a FIELD name, not a variable
        for f in dataclasses.fields(e):
            v = getattr(e, f.name)
            if isinstance(v, ASTNode):
                self.expr(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, ASTNode):
                        self.expr(item)

    def program(self, p):
        self.push()
        for m in p.modules:
            self.push()
            self.stmts(m.body.statements)
            self.pop()
        self.pop()
        return p


def compile_renamed(src):
    ast = parse_src(src)
    Renamer().program(ast)
    return compile_to_wasm(ast)


def main():
    src = ("module m { func main() type int { let x = 1"
           " if 1 == 1 then { let x = 99 } else { } return x } }")
    try:
        wat = compile_renamed(src)
        rv, _ = run_wat(wat)
        locals_ = [l.strip() for l in wat.splitlines() if l.strip().startswith("(local")]
        ok = (rv == 1)
        detail = f"returned {rv} (correct 1); locals: {locals_}"
        return verdict("001-lexical-scoping", ok, detail)
    except Exception as exc:
        return verdict("001-lexical-scoping", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
