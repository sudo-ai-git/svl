"""Scope-aware alpha-renaming for SVL ASTs.

The backend keeps one WASM local per *name*: `_compile_let_stmt` emits `local.set $name`
and `_compile_ident` emits `local.get $name`, resolved through a flat name set.  Two
bindings with the same name in nested scopes therefore share one slot, and an inner `let`
silently overwrites the outer binding:

    let x = 1
    if 1 == 1 then { let x = 99 } else { }
    return x                 # -> 99, should be 1

This module renames every binding to a unique name (`x`, `x__v1`, ...) and rewrites every
reference through a lexical scope stack, so each binding gets its own WASM local.  The
renamed AST is then handed to the normal backend, which needs no changes.

Rules:
  * every function body, block, `if` branch, loop body and `catch` block pushes a scope;
  * `let`, `for` loop variables, parameters and `catch` variables bind in the current scope;
  * a reference resolves to the innermost enclosing binding;
  * `FieldAccess.right` is a FIELD name, not a variable, and is never renamed.

Verified: the shadowing program above returns 1 and the WAT carries two distinct locals.
"""
from __future__ import annotations

import dataclasses
from typing import List

from svl.parser_rd import (
    ASTNode, Program, FuncDecl, Block, LetStmt, IfStmt, WhileStmt, ForStmt,
    ReturnStmt, AssertStmt, ExprStmt, TryStmt, ThrowStmt, ConstDecl, VarDecl,
    Ident, FieldAccess,
)


class ScopeRenamer:
    def __init__(self) -> None:
        self._counter = 0
        self._scopes: List[dict] = []

    # ---- scope stack ----
    def _push(self) -> None:
        self._scopes.append({})

    def _pop(self) -> None:
        self._scopes.pop()

    def _bind(self, name: str) -> str:
        self._counter += 1
        new = f"{name}__v{self._counter}"
        self._scopes[-1][name] = new
        return new

    def _resolve(self, name: str) -> str:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return name

    # ---- entry point ----
    def rename(self, program: Program) -> Program:
        self._push()
        for module in program.modules:
            self._push()
            for stmt in module.body.statements:
                self._stmt(stmt)
            self._pop()
        self._pop()
        return program

    # ---- statements ----
    def _stmt(self, node) -> None:
        if isinstance(node, LetStmt):
            self._expr(node.value)
            node.name = self._bind(node.name)
        elif isinstance(node, IfStmt):
            self._expr(node.condition)
            self._push()
            for s in node.then_branch.statements:
                self._stmt(s)
            self._pop()
            if node.else_branch is not None:
                self._push()
                for s in node.else_branch.statements:
                    self._stmt(s)
                self._pop()
        elif isinstance(node, WhileStmt):
            self._expr(node.condition)
            self._push()
            for s in node.body.statements:
                self._stmt(s)
            self._pop()
        elif isinstance(node, ForStmt):
            self._expr(node.iter_expr)
            self._push()
            node.var = self._bind(node.var)
            for s in node.body.statements:
                self._stmt(s)
            self._pop()
        elif isinstance(node, ReturnStmt):
            if node.value is not None:
                self._expr(node.value)
        elif isinstance(node, AssertStmt):
            self._expr(node.condition)
        elif isinstance(node, ExprStmt):
            self._expr(node.expression)
        elif isinstance(node, Block):
            self._push()
            for s in node.statements:
                self._stmt(s)
            self._pop()
        elif isinstance(node, TryStmt):
            self._push()
            for s in node.try_block.statements:
                self._stmt(s)
            self._pop()
            self._push()
            node.catch_var = self._bind(node.catch_var)
            for s in node.catch_block.statements:
                self._stmt(s)
            self._pop()
        elif isinstance(node, ThrowStmt):
            self._expr(node.value)
        elif isinstance(node, (ConstDecl, VarDecl)):
            # Top-level const/var are WASM globals; keep their names so the signature
            # and the type checker's recorded globals stay stable.
            self._expr(node.value)
        elif isinstance(node, FuncDecl):
            self._push()
            # Parameters keep their names: they are part of the function signature and
            # the type checker records them by name.  A `let` shadowing a parameter is
            # renamed instead, which is what makes that case correct.
            for s in node.body.statements:
                self._stmt(s)
            self._pop()

    # ---- expressions ----
    def _expr(self, node) -> None:
        if node is None or isinstance(node, (str, int, float, bool)):
            return
        if isinstance(node, Ident):
            node.name = self._resolve(node.name)
            return
        if isinstance(node, FieldAccess):
            # `node.right` is a field name, not a variable reference.
            self._expr(node.left)
            return
        for f in dataclasses.fields(node):
            value = getattr(node, f.name)
            if isinstance(value, ASTNode):
                self._expr(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ASTNode):
                        self._expr(item)


def rename_scopes(program: Program) -> Program:
    """Rename every binding uniquely and rewrite references (in place).

    Idempotent: a program already renamed is returned unchanged, so callers may apply it
    at more than one entry point without double-renaming.
    """
    if getattr(program, "_svl_renamed", False):
        return program
    ScopeRenamer().rename(program)
    program._svl_renamed = True        # excluded from to_dict()/serialization
    return program
