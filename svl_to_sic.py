#!/usr/bin/env python3
"""
SVL -> SIC/XE Compiler

Compiles SVL source code to SIC/XE assembly, assembles it with 231-gate
tamper-evident object code, and runs it in the verified simulator.

Pipeline:
  SVL source -> lex/parse -> SIC/XE assembly -> 231-gate stamped object code
  -> QEC-protected simulator execution

Usage:
  python3 svl_to_sic.py <source.svl>
  python3 svl_to_sic.py <source.svl> --emit-asm
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from svl.lexer import tokenize
from svl.parser_rd import (
    Parser, Program, Module, FuncDecl, Block, LetStmt, IfStmt, WhileStmt,
    ReturnStmt, AssertStmt, ExprStmt, BinaryExpr, UnaryExpr, CallExpr,
    Ident, Literal, TernaryExpr, ForStmt, Param, AssignExpr,
    IndexExpr,
)
from svl.gate231 import compute_checksums as gate231_compute_checksums
from sic_xe_assembler_sim import Assembler, Simulator, parse_source


class SICXECodeGen:
    def __init__(self):
        self.lines = []
        self.var_addr = {}
        self.var_slots = []               # (label, size_in_words) to emit as RESW
        self.slot_n = 0
        self.string_pool = {}
        self.label_n = 0
        self.param_addr = {}
        self.param_base = 0xF000          # fixed absolute arg-passing region (shared across objects)
        self.pending_label = None
        self.in_main = False

    def new_label(self, prefix="L"):
        self.label_n += 1
        return f"{prefix}{self.label_n}"

    def _new_slot(self, size=1):
        label = f"V{self.slot_n}"
        self.slot_n += 1
        self.var_slots.append((label, size))
        return label

    def alloc_var(self, name, size=1):
        """Allocate a relocatable variable slot; returns a label."""
        if name not in self.var_addr:
            self.var_addr[name] = self._new_slot(size)
        return self.var_addr[name]

    def alloc_slot(self, name, size=1):
        """Allocate an anonymous relocatable slot; returns a label."""
        return self._new_slot(size)

    def param_slot(self, index):
        """Fixed absolute argument slot (shared convention across objects)."""
        return self.param_base + 3 * index

    def alloc_string(self, text):
        if text not in self.string_pool:
            self.string_pool[text] = f"STR{len(self.string_pool)}"
        return self.string_pool[text]

    def emit(self, opcode, operand="", comment="", label=""):
        if label == "" and self.pending_label is not None:
            label = self.pending_label
            self.pending_label = None
        self.lines.append((label, opcode, operand, comment))

    def emit_comment(self, text):
        self.lines.append(("", "", "", text))

    def emit_directive(self, directive, operand="", comment=""):
        self.emit(directive, operand, comment)

    def emit_label(self, label):
        self.pending_label = label

    def emit_addr(self, opcode, addr, comment="", label=""):
        if isinstance(addr, str):
            # relocatable label reference
            self.emit(opcode, addr, comment, label)
        elif addr > 4095:
            self.emit("+" + opcode, str(addr), comment, label)
        else:
            self.emit(opcode, str(addr), comment, label)

    def compile(self, program):
        self.emit("START", "1000", comment="program entry")
        self._preallocate(program)
        self.emit_comment("runtime subroutines and data")
        self._emit_runtime()
        for module in program.modules:
            self._compile_module(module)
        for text, label in self.string_pool.items():
            self.emit_label(label)
            bytes_data = text.encode("ascii") + b"\x00"
            hex_str = "".join(f"{b:02X}" for b in bytes_data)
            self.emit_comment(f"string @ {label}: {text!r}")
            self.emit_directive("BYTE", f"X'{hex_str}'", comment=f"{label} ({len(bytes_data)} bytes)")
        for label, size in self.var_slots:
            self.emit_label(label)
            self.emit_directive("RESW", str(size), comment=f"variable {label} ({size} words)")
        self.emit_label("HALT")
        self.emit("HALT", comment="halt - end of program")
        self.emit("END", "MAIN", comment="entry point")
        return self.lines

    def _preallocate(self, program):
        for module in program.modules:
            self._preallocate_block(module.body)

    def _preallocate_block(self, block):
        for stmt in block.statements:
            self._preallocate_stmt(stmt)

    def _preallocate_stmt(self, stmt):
        t = stmt.type.value
        if t == "LetStmt":
            if not getattr(stmt, "array_size", None):
                self.alloc_var(stmt.name)
            self._preallocate_expr(stmt.value)
        elif t == "IfStmt":
            self._preallocate_expr(stmt.condition)
            self._preallocate_block(stmt.then_branch)
            if stmt.else_branch:
                self._preallocate_block(stmt.else_branch)
        elif t == "WhileStmt":
            self._preallocate_expr(stmt.condition)
            self._preallocate_block(stmt.body)
        elif t == "ForStmt":
            self._preallocate_expr(stmt.iter_expr)
            self._preallocate_block(stmt.body)
        elif t == "ReturnStmt":
            if stmt.value:
                self._preallocate_expr(stmt.value)
        elif t == "AssertStmt":
            self._preallocate_expr(stmt.condition)
        elif t == "ExprStmt":
            self._preallocate_expr(stmt.expression)
        elif t == "Block":
            self._preallocate_block(stmt)

    def _preallocate_expr(self, expr):
        if expr is None:
            return
        t = expr.type.value
        if t == "BinaryExpr":
            self._preallocate_expr(expr.left)
            self._preallocate_expr(expr.right)
        elif t == "UnaryExpr":
            self._preallocate_expr(expr.operand)
        elif t == "CallExpr":
            for arg in expr.arguments:
                self._preallocate_expr(arg)
        elif t == "TernaryExpr":
            self._preallocate_expr(expr.condition)
            self._preallocate_expr(expr.then_expr)
            self._preallocate_expr(expr.else_expr)
        elif t == "Ident":
            self.alloc_var(expr.name)
        elif t == "Literal":
            if expr.literal_type == "string":
                self.alloc_string(expr.value)

    def _compile_module(self, module):
        self.emit_comment(f"module {module.name}")
        stmts = list(module.body.statements)
        main_stmts = [s for s in stmts if s.type.value == "FuncDecl" and getattr(s, "name", None) == "main"]
        other_stmts = [s for s in stmts if not (s.type.value == "FuncDecl" and getattr(s, "name", None) == "main")]
        ordered = main_stmts + other_stmts
        for stmt in ordered:
            if stmt.type.value == "FuncDecl" and getattr(stmt, "name", None):
                self.emit_label(stmt.name)
        for stmt in ordered:
            self._compile_stmt(stmt)

    def _compile_stmt(self, stmt):
        t = stmt.type.value
        if t == "LetStmt":
            self._compile_let(stmt)
        elif t == "IfStmt":
            self._compile_if(stmt)
        elif t == "WhileStmt":
            self._compile_while(stmt)
        elif t == "ForStmt":
            self._compile_for(stmt)
        elif t == "ReturnStmt":
            self._compile_return(stmt)
        elif t == "AssertStmt":
            self._compile_assert(stmt)
        elif t == "ExprStmt":
            self._compile_expr_stmt(stmt)
        elif t == "FuncDecl":
            self._compile_func_decl(stmt)
        elif t == "Block":
            for s in stmt.statements:
                self._compile_stmt(s)
        else:
            self.emit_comment(f"unhandled stmt: {stmt.type}")

    def _compile_func_decl(self, func):
        func_name = func.name
        self.emit_label(func_name)
        self.emit_comment(f"function {func.name}")
        for i, param in enumerate(func.params):
            self.param_addr[param.name] = self.param_slot(i)
        self.in_main = (func.name == "main")
        if not self.in_main:
            # Save return address L before any built-in calls can clobber it
            self.emit("STL", "L_SAVE", comment="save return address L")
        self._compile_block(func.body)
        if func.body.statements:
            last = func.body.statements[-1]
            if last.type.value != "ReturnStmt":
                if self.in_main:
                    self.emit("HALT", comment="halt")
                else:
                    # Restore return address L before returning to caller
                    self.emit("LDL", "L_SAVE", comment="restore return address L")
                    self.emit("RSUB", comment="implicit return")
        else:
            if self.in_main:
                self.emit("HALT", comment="halt")
            else:
                self.emit("LDL", "L_SAVE", comment="restore return address L")
                self.emit("RSUB", comment="empty function")
        self.in_main = False

    def _compile_let(self, stmt):
        if stmt.array_size:
            # Array layout: a slot holding the data pointer, then `size` words.
            self._compile_expr(stmt.array_size)
            size_slot = self.alloc_slot(f"{stmt.name}_asize")
            self.emit_addr("STA", size_slot, comment=f"array size for {stmt.name}")
            if isinstance(stmt.array_size, Literal):
                size_val = stmt.array_size.value
            else:
                size_val = 10
            base_slot = self.alloc_slot(f"{stmt.name}_base")
            data_slot = self.alloc_slot(f"{stmt.name}_data", size_val)
            self.var_addr[stmt.name] = base_slot
            self.emit("LDA", f"#{data_slot}", comment=f"data address for {stmt.name}")
            self.emit_addr("STA", base_slot, comment=f"store data pointer for {stmt.name}")
        else:
            addr = self.alloc_var(stmt.name)
            self.emit_comment(f"let {stmt.name} = ...  @ {addr}")
            self._compile_expr(stmt.value)
            self.emit_addr("STA", addr, comment=f"store {stmt.name}")

    def _compile_if(self, stmt):
        end_label = self.new_label("endif")
        # With no else branch, jump straight to the end: emit_label would
        # otherwise overwrite else_label and leave it undefined (-> 0).
        else_label = self.new_label("else") if stmt.else_branch else end_label
        self._compile_expr(stmt.condition)
        self.emit("COMP", "ZERO", comment="condition == 0?")
        self.emit("JEQ", else_label, comment="if false -> else")
        self._compile_block(stmt.then_branch)
        if stmt.else_branch:
            self.emit("J", end_label, comment="skip else")
            self.emit_label(else_label)
            self._compile_block(stmt.else_branch)
        self.emit_label(end_label)

    def _compile_while(self, stmt):
        loop_label = self.new_label("while")
        exit_label = self.new_label("endwhile")
        self.emit_label(loop_label)
        self._compile_expr(stmt.condition)
        self.emit("COMP", "ZERO", comment="condition == 0?")
        self.emit("JEQ", exit_label, comment="exit loop if false")
        self._compile_block(stmt.body)
        self.emit("J", loop_label, comment="repeat")
        self.emit_label(exit_label)

    def _compile_for(self, stmt):
        iter_expr = stmt.iter_expr
        if iter_expr.type.value != "BinaryExpr" or iter_expr.operator != "..":
            self.emit_comment("unsupported for loop iterator")
            return
        start_expr = iter_expr.left
        end_expr = iter_expr.right
        self._compile_expr(start_expr)
        self.emit_addr("STA", self.alloc_var(stmt.var), comment=f"init {stmt.var}")
        loop_label = self.new_label("while")
        end_label = self.new_label("endwhile")
        self.emit_label(loop_label)
        self.emit_addr("LDA", self.var_addr[stmt.var], comment=f"load {stmt.var}")
        self.emit("STA", "TMP0", comment="save var")
        self._compile_expr(end_expr)
        self.emit("STA", "TMP1", comment="save end")
        self.emit("LDA", "TMP0", comment="reload var")
        self.emit("COMP", "TMP1", comment=f"compare {stmt.var} < end")
        self.emit("JGT", end_label, comment="exit if var > end")
        self._compile_block(stmt.body)
        self.emit_addr("LDA", self.var_addr[stmt.var], comment=f"load {stmt.var}")
        self.emit("ADD", "#1", comment="var + 1")
        self.emit_addr("STA", self.var_addr[stmt.var], comment=f"store {stmt.var}")
        self.emit("J", loop_label, comment="repeat loop")
        self.emit_label(end_label)

    def _compile_return(self, stmt):
        if stmt.value:
            self._compile_expr(stmt.value)
            self.emit("STA", "RETVAL", comment="return value")
        if self.in_main:
            self.emit("HALT", comment="halt - return from main")
        else:
            self.emit("RSUB", comment="return")

    def _compile_assert(self, stmt):
        self._compile_expr(stmt.condition)
        self.emit("COMP", "ZERO", comment="assert condition == 0?")
        self.emit("JEQ", "ASSERT_FAIL", comment="fail if zero")

    def _compile_expr_stmt(self, stmt):
        expr = stmt.expression
        if isinstance(expr, AssignExpr):
            self._compile_assign(expr)
        else:
            self._compile_expr(expr)

    def _compile_assign(self, expr):
        target = expr.target
        op = expr.operator
        value = expr.value

        if isinstance(target, IndexExpr):
            arr_name = target.left.name
            index_expr = target.right
            self.emit_addr("LDA", self.var_addr[arr_name], comment=f"load base of {arr_name}")
            self.emit("STA", "TMP3", comment="save base addr")
            self._compile_expr(index_expr)
            self.emit("MUL", "#3", comment="index * 3 (word size)")
            self.emit("ADD", "TMP3", comment="base + index*3")
            # Stash the target in TMP4: evaluating the value below may itself
            # be an array access, which reuses IND.
            self.emit("STA", "TMP4", comment="TMP4 = element address")
            self._compile_expr(value)
            self.emit("STA", "@TMP4", comment=f"store value at {arr_name}[index]")
            return

        target_name = target.name if isinstance(target, Ident) else str(target)
        if op == "=":
            self._compile_expr(value)
            addr = self.alloc_var(target_name)
            self.emit_addr("STA", addr, comment=f"store {target_name}")
        else:
            op_map = {
                "+=": "+",
                "-=": "-",
                "*=": "*",
                "/=": "/",
                "%=": "%",
                "&=": "&",
                "|=": "|",
                "^=": "^",
                "<<=": "<<",
                ">>=": ">>",
            }
            base_op = op_map.get(op)
            if base_op is None:
                self.emit_comment(f"unhandled compound assign: {op}")
                return
            # Fresh slots: the value expression may itself be a binary/array
            # expression that reuses TMP0/TMP1.
            lslot = self.alloc_slot("asgnL")
            rslot = self.alloc_slot("asgnR")
            self.emit_addr("LDA", self.alloc_var(target_name), comment=f"load {target_name}")
            self.emit_addr("STA", lslot, comment="save target")
            self._compile_expr(value)
            self.emit_addr("STA", rslot, comment="save right")
            self.emit_addr("LDA", lslot, comment="reload target")
            if base_op == "+":
                self.emit_addr("ADD", rslot, comment=f"{target_name} + right")
            elif base_op == "-":
                self.emit_addr("SUB", rslot, comment=f"{target_name} - right")
            elif base_op == "*":
                self.emit_addr("MUL", rslot, comment=f"{target_name} * right")
            elif base_op == "/":
                self.emit_addr("DIV", rslot, comment=f"{target_name} / right")
            elif base_op == "%":
                # MOD computes A % MOD_ARG, so the divisor is the RIGHT operand
                self.emit_addr("LDA", rslot, comment="right operand")
                self.emit_addr("STA", "MOD_ARG", comment="set mod divisor")
                self.emit_addr("LDA", lslot, comment="left operand")
                self.emit("JSUB", "MOD", comment=f"{target_name} % right")
            elif base_op == "&":
                self.emit_addr("AND", rslot, comment=f"{target_name} & right")
            elif base_op == "|":
                self.emit_addr("OR", rslot, comment=f"{target_name} | right")
            elif base_op == "^":
                # XOR computes A ^ XOR_ARG, so the mask is the RIGHT operand
                self.emit_addr("LDA", rslot, comment="right operand")
                self.emit_addr("STA", "XOR_ARG", comment="set xor mask")
                self.emit_addr("LDA", lslot, comment="left operand")
                self.emit("JSUB", "XOR", comment=f"{target_name} ^ right")
            elif base_op == "<<":
                self.emit_addr("LDA", rslot, comment="shift amount")
                self.emit("STA", "SHL_ARG", comment="set shl amount")
                self.emit_addr("LDA", lslot, comment="value to shift")
                self.emit("JSUB", "SHL", comment=f"{target_name} << right")
            elif base_op == ">>":
                self.emit_addr("LDA", rslot, comment="shift amount")
                self.emit("STA", "SHR_ARG", comment="set shr amount")
                self.emit_addr("LDA", lslot, comment="value to shift")
                self.emit("JSUB", "SHR", comment=f"{target_name} >> right")
            addr = self.alloc_var(target_name)
            self.emit_addr("STA", addr, comment=f"store {target_name}")

    def _compile_expr(self, expr):
        if expr is None:
            return
        if isinstance(expr, Literal):
            self._compile_literal(expr)
        elif isinstance(expr, Ident):
            self._compile_ident(expr)
        elif isinstance(expr, BinaryExpr):
            self._compile_binary(expr)
        elif isinstance(expr, UnaryExpr):
            self._compile_unary(expr)
        elif isinstance(expr, CallExpr):
            self._compile_call(expr)
        elif isinstance(expr, TernaryExpr):
            self._compile_ternary(expr)
        elif isinstance(expr, AssignExpr):
            self._compile_assign(expr)
        elif isinstance(expr, IndexExpr):
            self._compile_index_expr(expr)
        else:
            self.emit_comment(f"unhandled expr: {type(expr).__name__}")

    def _compile_index_expr(self, expr):
        """Compile a read of arr[index] into A.

        Layout: arr's slot holds the data pointer; elements are 3-byte words.
        """
        arr_name = expr.left.name
        index_expr = expr.right
        # Use TMP3 (not TMP0/TMP1) so a surrounding expression's operands survive
        self.emit_addr("LDA", self.var_addr[arr_name], comment=f"load base of {arr_name}")
        self.emit("STA", "TMP3", comment="save base addr")
        self._compile_expr(index_expr)
        self.emit("MUL", "#3", comment="index * 3 (word size)")
        self.emit("ADD", "TMP3", comment="base + index*3")
        self.emit("STA", "IND", comment="IND = element address")
        self.emit("LDA", "@IND", comment=f"load {arr_name}[index]")

    def _compile_literal(self, expr):
        lt = expr.literal_type
        v = expr.value
        if lt == "int":
            self.emit("LDA", f"#{v}", comment=f"load {v}")
        elif lt == "string":
            addr = self.alloc_string(v)
            safe = v.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\t", "\\t")
            self.emit("LDA", f"#{addr}", comment=f'load string addr "{safe}"')
        elif lt == "bool":
            self.emit("LDA", f"#{1 if v else 0}", comment=f"load bool {v}")
        else:
            self.emit_comment(f"unhandled literal type: {lt}")

    def _compile_ident(self, expr):
        name = expr.name
        if name in self.param_addr:
            self.emit_addr("LDA", self.param_addr[name], comment=f"load param {name}")
        else:
            addr = self.alloc_var(name)
            self.emit_addr("LDA", addr, comment=f"load {name}")

    def _compile_binary(self, expr):
        op = expr.operator
        left = expr.left
        right = expr.right
        # Each binary node gets its OWN operand slots: fixed TMP0/TMP1 are not
        # reentrant, so a nested expression (e.g. `j < n - 1`) would clobber
        # the enclosing node's saved operands.
        lslot = self.alloc_slot("lhs")
        rslot = self.alloc_slot("rhs")

        if op in ("==", "!=", "<", ">", "<=", ">="):
            self._compile_expr(left)
            self.emit_addr("STA", lslot, comment="save left")
            self._compile_expr(right)
            self.emit_addr("STA", rslot, comment="save right")
            self.emit_addr("LDA", lslot, comment="reload left")
            self.emit_addr("COMP", rslot, comment=f"compare {op}")
            # Convert SW to boolean in A (1 = true, 0 = false)
            true_label = self.new_label("cmp_true")
            done_label = self.new_label("cmp_done")
            self.emit("LDA", "#0", comment="default false")
            jump_map = {
                "==": "JEQ",
                "!=": "JNE",
                "<": "JLT",
                ">": "JGT",
                "<=": "JLE",
                ">=": "JGE",
            }
            self.emit(jump_map[op], true_label, comment=f"if {op} -> true")
            self.emit("J", done_label, comment="skip true")
            self.emit_label(true_label)
            self.emit("LDA", "#1", comment="true")
            self.emit_label(done_label)
            return

        self._compile_expr(left)
        self.emit_addr("STA", lslot, comment="save left")
        self._compile_expr(right)
        self.emit_addr("STA", rslot, comment="save right")

        op_map = {
            "+": "ADD",
            "-": "SUB",
            "*": "MUL",
            "/": "DIV",
            "&": "AND",
            "|": "OR",
        }
        if op in op_map:
            self.emit_addr("LDA", lslot, comment="reload left")
            self.emit(op_map[op], rslot, comment=f"{op} right")
        elif op == "%":
            # left % right = left - (left / right) * right
            qslot = self.alloc_slot("quot")
            pslot = self.alloc_slot("prod")
            self.emit_addr("LDA", lslot, comment="left operand")
            self.emit_addr("DIV", rslot, comment="left / right")
            self.emit_addr("STA", qslot, comment="save quotient")
            self.emit_addr("MUL", rslot, comment="quotient * right")
            self.emit_addr("STA", pslot, comment="save product")
            self.emit_addr("LDA", lslot, comment="reload left")
            self.emit_addr("SUB", pslot, comment="left - product = left % right")
        elif op == "^":
            # left ^ right = (left | right) - (left & right)
            oslot = self.alloc_slot("orv")
            aslot = self.alloc_slot("andv")
            self.emit_addr("LDA", lslot, comment="reload left")
            self.emit_addr("OR", rslot, comment="left | right")
            self.emit_addr("STA", oslot, comment="save left|right")
            self.emit_addr("LDA", lslot, comment="reload left")
            self.emit_addr("AND", rslot, comment="left & right")
            self.emit_addr("STA", aslot, comment="save left&right")
            self.emit_addr("LDA", oslot, comment="reload left|right")
            self.emit_addr("SUB", aslot, comment="(left|right)-(left&right) = left^right")
        elif op == "<<":
            # shift amount is the RIGHT operand; value is the left
            self.emit_addr("LDA", rslot, comment="shift amount")
            self.emit("STA", "SHL_ARG", comment="set shl amount")
            self.emit_addr("LDA", lslot, comment="value to shift")
            self.emit("JSUB", "SHL", comment=f"{op} right")
        elif op == ">>":
            self.emit_addr("LDA", rslot, comment="shift amount")
            self.emit("STA", "SHR_ARG", comment="set shr amount")
            self.emit_addr("LDA", lslot, comment="value to shift")
            self.emit("JSUB", "SHR", comment=f"{op} right")

    def _compile_unary(self, expr):
        op = expr.operator
        self._compile_expr(expr.operand)
        if op == "-":
            self.emit("STA", "TMP0", comment="save operand")
            self.emit("LDA", "#0", comment="0 - operand")
            self.emit("SUB", "TMP0", comment="negate")
        elif op == "~":
            # Inline NOT: ~x = -x - 1 (2's complement)
            self.emit("STA", "TMP0", comment="save operand")
            self.emit("LDA", "#0", comment="0 - operand")
            self.emit("SUB", "TMP0", comment="-operand")
            self.emit("SUB", "#1", comment="-operand - 1 = ~operand")
        elif op == "!":
            # !x = 1 if x == 0 else 0
            done = self.new_label("not_done")
            self.emit("COMP", "#0", comment="is operand zero?")
            self.emit("LDA", "#0", comment="default: not zero -> 0")
            self.emit("JNE", done, comment="non-zero -> false")
            self.emit("LDA", "#1", comment="zero -> true")
            self.emit_label(done)
        else:
            self.emit_comment(f"unhandled unary op: {op}")

    def _compile_ternary(self, expr):
        end_label = self.new_label("endtern")
        else_label = self.new_label("ternelse")
        slot = self.alloc_slot("tern")   # per-node: nested ternaries must not clash
        self._compile_expr(expr.condition)
        self.emit("COMP", "#0", comment="condition == 0?")
        self.emit("JEQ", else_label, comment="if false -> else branch")
        self._compile_expr(expr.then_expr)
        self.emit_addr("STA", slot, comment="save then result")
        self.emit("J", end_label, comment="skip else")
        self.emit_label(else_label)
        self._compile_expr(expr.else_expr)
        self.emit_addr("STA", slot, comment="save else result")
        self.emit_label(end_label)
        self.emit_addr("LDA", slot, comment="load ternary result")

    def _compile_call(self, expr):
        callee = expr.callee
        args = expr.arguments
        if callee == "print_int":
            if args:
                self._compile_expr(args[0])
                self.emit("+JSUB", "65280", comment="print_int(arg)")
            return
        if callee == "print":
            if args:
                self._compile_expr(args[0])
                self.emit("+JSUB", "65283", comment="print(string)")
            return
        if callee == "svc_open":
            if args:
                self._compile_expr(args[0])
                self.emit_addr("STA", 0xFF13, comment="SVC name addr")
                self.emit("LDA", "#3", comment="SVC open")
                self.emit_addr("STA", 0xFF07, comment="SVC number = 3")
                self.emit("+JSUB", "65286", comment="SVC open(name) -> fd in A")
            return
        if callee == "svc_create":
            if args:
                self._compile_expr(args[0])
                self.emit_addr("STA", 0xFF13, comment="SVC name addr")
                self.emit("LDA", "#8", comment="SVC create")
                self.emit_addr("STA", 0xFF07, comment="SVC number = 8")
                self.emit("+JSUB", "65286", comment="SVC create(name) -> fd in A (write mode)")
            return
        if callee == "svc_read":
            if len(args) >= 3:
                self._compile_expr(args[0])
                self.emit_addr("STA", 0xFF0A, comment="SVC fd")
                self._compile_expr(args[1])
                self.emit_addr("STA", 0xFF0D, comment="SVC buf")
                self._compile_expr(args[2])
                self.emit_addr("STA", 0xFF10, comment="SVC count")
                self.emit("LDA", "#4", comment="SVC read = 4")
                self.emit_addr("STA", 0xFF07, comment="SVC number = 4")
                self.emit("+JSUB", "65286", comment="SVC read(fd, buf, count) -> A")
            return
        if callee == "svc_write":
            if len(args) >= 3:
                self._compile_expr(args[0])
                self.emit_addr("STA", 0xFF0A, comment="SVC fd")
                self._compile_expr(args[1])
                self.emit_addr("STA", 0xFF0D, comment="SVC buf")
                self._compile_expr(args[2])
                self.emit_addr("STA", 0xFF10, comment="SVC count")
                self.emit("LDA", "#5", comment="SVC write = 5")
                self.emit_addr("STA", 0xFF07, comment="SVC number = 5")
                self.emit("+JSUB", "65286", comment="SVC write(fd, buf, count) -> bytes written in A")
            return
        if callee == "svc_close":
            if args:
                self._compile_expr(args[0])
                self.emit_addr("STA", 0xFF0A, comment="SVC fd")
                self.emit("LDA", "#6", comment="SVC close")
                self.emit_addr("STA", 0xFF07, comment="SVC number = 6")
                self.emit("+JSUB", "65286", comment="SVC close(fd)")
            return
        if callee == "svc_exit":
            if args:
                self._compile_expr(args[0])
                self.emit_addr("STA", 0xFF0A, comment="SVC exit code")
                self.emit("LDA", "#7", comment="SVC exit")
                self.emit_addr("STA", 0xFF07, comment="SVC number = 7")
                self.emit("+JSUB", "65286", comment="SVC exit(code)")
            return
        param_index = 0
        for arg in args:
            self._compile_expr(arg)
            self.emit_addr("STA", self.param_slot(param_index), comment=f"param[{param_index}]")
            param_index += 1
        self.emit("JSUB", callee, comment=f"call {callee}")


    def _emit_runtime(self):
        # Runtime subroutines
        # Assertion failure handler: report and halt (previously the label was
        # referenced but never defined, so a failing assert jumped to address 0).
        self.emit_label("ASSERT_FAIL")
        fail_msg = self.alloc_string("ASSERT FAILED\n")
        self.emit("LDA", f"#{fail_msg}", comment="load failure message")
        self.emit("+JSUB", "65283", comment="print failure message")
        self.emit("HALT", comment="halt on assertion failure")

        self.emit_label("ZERO")
        self.emit_directive("WORD", "0", comment="constant 0")
        self.emit_label("RETVAL")
        self.emit_directive("WORD", "0", comment="return value")
        self.emit_label("TMP0")
        self.emit_directive("WORD", "0", comment="temp 0")
        self.emit_label("TMP1")
        self.emit_directive("WORD", "0", comment="temp 1")
        self.emit_label("TMP2")
        self.emit_directive("WORD", "0", comment="temp 2")
        self.emit_label("TMP3")
        self.emit_directive("WORD", "0", comment="temp 3 (array base)")
        self.emit_label("TMP4")
        self.emit_directive("WORD", "0", comment="temp 4")
        self.emit_label("MOD_ARG")
        self.emit_directive("WORD", "0", comment="mod divisor")
        self.emit_label("SHL_ARG")
        self.emit_directive("WORD", "0", comment="shift amount")
        self.emit_label("SHR_ARG")
        self.emit_directive("WORD", "0", comment="shift amount")
        self.emit_label("XOR_ARG")
        self.emit_directive("WORD", "0", comment="xor mask")
        self.emit_label("NOT_ARG")
        self.emit_directive("WORD", "0", comment="not operand")
        self.emit_label("TERN_RESULT")
        self.emit_directive("WORD", "0", comment="ternary result")
        self.emit_label("L_SAVE")
        self.emit_directive("WORD", "0", comment="saved return address L")
        self.emit_label("IND")
        self.emit_directive("WORD", "0", comment="indirect element address for arrays")
        self.emit_label("MOD")
        self.emit_comment("MOD: A = A % MOD_ARG (24-bit, unsigned)")
        self.emit("STA", "MOD_DIVIDEND", comment="save dividend")
        self.emit("LDA", "MOD_ARG", comment="load divisor")
        self.emit("STA", "MOD_DIVISOR", comment="save divisor")
        self.emit("LDA", "MOD_DIVIDEND", comment="reload dividend")
        self.emit("DIV", "MOD_DIVISOR", comment="A = dividend / divisor")
        self.emit("STA", "MOD_QUOTIENT", comment="save quotient")
        self.emit("MUL", "MOD_DIVISOR", comment="A = quotient * divisor")
        self.emit("STA", "MOD_PRODUCT", comment="save product")
        self.emit("LDA", "MOD_DIVIDEND", comment="reload dividend")
        self.emit("SUB", "MOD_PRODUCT", comment="A = dividend - product = remainder")
        self.emit("RSUB", comment="return")
        self.emit_label("MOD_DIVIDEND")
        self.emit_directive("WORD", "0")
        self.emit_label("MOD_DIVISOR")
        self.emit_directive("WORD", "0")
        self.emit_label("MOD_QUOTIENT")
        self.emit_directive("WORD", "0")
        self.emit_label("MOD_PRODUCT")
        self.emit_directive("WORD", "0")
        self.emit_label("XOR")
        self.emit_comment("XOR: A = A ^ XOR_ARG = (A | B) - (A & B)")
        self.emit("STA", "XOR_LEFT", comment="save left")
        self.emit("LDA", "XOR_ARG", comment="load right")
        self.emit("STA", "XOR_RIGHT", comment="save right")
        self.emit("LDA", "XOR_LEFT", comment="reload left")
        self.emit("OR", "XOR_RIGHT", comment="A = left | right")
        self.emit("STA", "XOR_OR", comment="save or")
        self.emit("LDA", "XOR_LEFT", comment="reload left")
        self.emit("AND", "XOR_RIGHT", comment="A = left & right")
        self.emit("STA", "XOR_AND", comment="save and")
        self.emit("LDA", "XOR_OR", comment="reload or")
        self.emit("SUB", "XOR_AND", comment="A = or - and = xor")
        self.emit("RSUB", comment="return")
        self.emit_label("XOR_LEFT")
        self.emit_directive("WORD", "0")
        self.emit_label("XOR_RIGHT")
        self.emit_directive("WORD", "0")
        self.emit_label("XOR_OR")
        self.emit_directive("WORD", "0")
        self.emit_label("XOR_AND")
        self.emit_directive("WORD", "0")
        self.emit_label("SHL")
        self.emit_comment("SHL: A = A << SHL_ARG (repeated doubling)")
        self.emit("STA", "SHL_VAL", comment="save value")
        self.emit("LDA", "SHL_ARG", comment="load shift count")
        self.emit("STA", "SHL_COUNT", comment="save count")
        self.emit("LDA", "SHL_VAL", comment="reload value")
        self.emit_label("SHL_LOOP")
        self.emit("LDA", "SHL_COUNT", comment="load count")
        self.emit("COMP", "#0", comment="count == 0?")
        self.emit("JEQ", "SHL_DONE", comment="if zero -> done")
        self.emit("LDA", "SHL_VAL", comment="reload value")
        self.emit("ADD", "SHL_VAL", comment="value = value + value (= << 1)")
        self.emit("STA", "SHL_VAL", comment="save value")
        self.emit("LDA", "SHL_COUNT", comment="reload count")
        self.emit("SUB", "#1", comment="count = count - 1")
        self.emit("STA", "SHL_COUNT", comment="save count")
        self.emit("J", "SHL_LOOP", comment="repeat")
        self.emit_label("SHL_DONE")
        self.emit("LDA", "SHL_VAL", comment="load final value")
        self.emit("RSUB", comment="return")
        self.emit_label("SHL_VAL")
        self.emit_directive("WORD", "0")
        self.emit_label("SHL_COUNT")
        self.emit_directive("WORD", "0")
        self.emit_label("SHR")
        self.emit_comment("SHR: A = A >> SHR_ARG (repeated halving via subtract powers of 2)")
        self.emit("STA", "SHR_VAL", comment="save value")
        self.emit("LDA", "SHR_ARG", comment="load shift count")
        self.emit("STA", "SHR_COUNT", comment="save count")
        self.emit("LDA", "SHR_VAL", comment="reload value")
        self.emit_label("SHR_LOOP")
        self.emit("LDA", "SHR_COUNT", comment="load count")
        self.emit("COMP", "#0", comment="count == 0?")
        self.emit("JEQ", "SHR_DONE", comment="if zero -> done")
        self.emit("LDA", "SHR_VAL", comment="reload value")
        self.emit("DIV", "#2", comment="A = value / 2 (= >> 1)")
        self.emit("STA", "SHR_VAL", comment="save value")
        self.emit("LDA", "SHR_COUNT", comment="reload count")
        self.emit("SUB", "#1", comment="count = count - 1")
        self.emit("STA", "SHR_COUNT", comment="save count")
        self.emit("J", "SHR_LOOP", comment="repeat")
        self.emit_label("SHR_DONE")
        self.emit("LDA", "SHR_VAL", comment="load final value")
        self.emit("RSUB", comment="return")
        self.emit_label("SHR_VAL")
        self.emit_directive("WORD", "0")
        self.emit_label("SHR_COUNT")
        self.emit_directive("WORD", "0")
        self.emit_label("NOT")
        self.emit_comment("NOT: A = ~A = -A - 1 (24-bit)")
        self.emit("STA", "NOT_VAL", comment="save operand")
        self.emit("LDA", "#0", comment="A = 0")
        self.emit("SUB", "NOT_VAL", comment="A = -operand")
        self.emit("SUB", "#1", comment="A = -operand - 1 = ~operand")
        self.emit("RSUB", comment="return")
        self.emit_label("NOT_VAL")
        self.emit_directive("WORD", "0")

    def _compile_block(self, block):
        for stmt in block.statements:
            self._compile_stmt(stmt)


def assembly_to_source(asm_lines):
    """Convert (label, opcode, operand, comment) tuples back to assembly source text."""
    lines = []
    for label, opcode, operand, comment in asm_lines:
        parts = []
        if label:
            parts.append(label)  # label without colon; parse_source handles it
        if opcode:
            parts.append(opcode)
        if operand:
            parts.append(operand)
        if comment:
            parts.append(f". {comment}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 svl_to_sic.py <source.svl> [--emit-asm] [--emit-obj]")
        return 1

    source_path = Path(sys.argv[1])
    emit_asm = "--emit-asm" in sys.argv
    emit_obj = "--emit-obj" in sys.argv

    svl_text = source_path.read_text()

    tokens = tokenize(svl_text)
    parser = Parser(tokens)
    ast = parser.parse()

    codegen = SICXECodeGen()
    asm_lines = codegen.compile(ast)

    if emit_asm:
        print("=" * 70)
        print("SIC/XE ASSEMBLY OUTPUT")
        print("=" * 70)
        for label, opcode, operand, comment in asm_lines:
            parts = []
            if label:
                parts.append(f"{label}:")
            if opcode:
                parts.append(opcode)
            if operand:
                parts.append(operand)
            if comment:
                parts.append(f". {comment}")
            print(" ".join(parts))

    asm_text = assembly_to_source(asm_lines)
    src_lines = parse_source(asm_text)

    asm = Assembler(src_lines)
    sym_path = str(source_path.with_suffix(".sym"))
    success, records = asm.assemble(write_symbol_file_path=sym_path)

    if not success:
        print("ASSEMBLY FAILED:")
        for err in asm.errors:
            print(f"  {err}")
        return 1

    if emit_obj:
        obj_path = str(source_path.with_suffix(".obj"))
        lines = [records["H"]]
        lines.extend(records["T"])
        lines.append(records["E"])
        Path(obj_path).write_text("\n".join(lines) + "\n")
        print(f"Wrote object file: {obj_path}")
        if not emit_asm:
            return 0

    print("")
    print("Summary:")
    num_symbols = len(asm.symtab)
    num_t_records = len(records["T"])
    print(f"  Symbols: {num_symbols}")
    print(f"  T records: {num_t_records}")
    print(f"  H: {records['H']}")
    for t in records["T"]:
        t_str = t[:80] + "..." if len(t) > 80 else t
        print(f"  T: {t_str}")
    print(f"  E: {records['E']}")

    sim = Simulator()
    try:
        start = sim.verify_and_load_records(records)
        print("")
        print(f"231-gate verification PASSED — entry at {start:06X}")
    except ValueError as e:
        print("")
        print(f"231-gate verification FAILED: {e}")
        return 1

    trace = sim.run()

    for line in trace:
        print(line)

    print("")
    print("--- Final Register State ---")
    for reg in ["A", "X", "L", "B", "S", "T", "F", "PC", "SW"]:
        print(f"  {reg} = {sim.regs[reg]:06X}")

    print("")
    print("=" * 70)
    print("SVL -> SIC/XE -> 231-gate verified object code -> executed")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
