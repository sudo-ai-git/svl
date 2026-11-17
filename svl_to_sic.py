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


# Runtime scratch slots at fixed absolute addresses (0xF000 block).
# Shared by every object file: each object carries its own copy of the runtime
# code, so if these were per-object labels a callee would get a different
# LSP/FPTR than its caller and its frames would land on top of the caller's.
SLOT_BASE = 0xF000
SLOT_ADDRS = {
    "LSP":        SLOT_BASE + 0,     # value/return stack pointer
    "FPTR":       SLOT_BASE + 3,     # frame pointer
    "IND":        SLOT_BASE + 6,     # indirect address scratch
    "TMP0":       SLOT_BASE + 9,
    "TMP1":       SLOT_BASE + 12,
    "TMP2":       SLOT_BASE + 15,
    "TMP3":       SLOT_BASE + 18,
    "TMP4":       SLOT_BASE + 21,
    "RETVAL":     SLOT_BASE + 24,
    "MOD_ARG":    SLOT_BASE + 27,
    "SHL_ARG":    SLOT_BASE + 30,
    "SHR_ARG":    SLOT_BASE + 33,
    "XOR_ARG":    SLOT_BASE + 36,
    "NOT_ARG":    SLOT_BASE + 39,
    "TERN_RESULT": SLOT_BASE + 42,
    "ZERO":       SLOT_BASE + 45,    # reads as 0; never written
}
PARAM_BASE = 0xF040                              # incoming argument slots


class SICXECodeGen:
    def __init__(self):
        self.lines = []
        self.var_addr = {}
        self.var_slots = []               # (label, size_in_words) to emit as RESW
        self.slot_n = 0
        self.string_pool = {}
        self.label_n = 0
        self.param_addr = {}
        self.param_base = PARAM_BASE      # fixed absolute arg-passing region (shared across objects)
        self.array_locals = set()         # names whose value is an element-block address
        self.pending_label = None
        self.in_main = False

    # Return-address/value stack (a single global slot is not enough for recursion)
    LSTACK_BASE = 0xF400
    LSTACK_FRAMES = 900      # region ends at 0xFEFC, below the SVC page at 0xFF06

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
        # Runtime scratch slots live at fixed absolute addresses. Each object
        # file carries its own copy of the runtime, so per-object slot labels
        # would give a callee a *different* stack pointer than its caller and
        # the callee's frames would overwrite the caller's.
        if isinstance(operand, str):
            core = operand.strip().lstrip("@#").replace(",X", "").strip()
            if core in SLOT_ADDRS:
                operand = operand.replace(core, str(SLOT_ADDRS[core]), 1)
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
        # Parameters and locals are frame-allocated per function by
        # _scan_frame, so there is nothing to preallocate here. (This pass
        # used to create fixed slots, which are exactly what recursion breaks.)
        return

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

        # Frame layout (growing up, LSP points just past the last word):
        #   [ret][saved FPTR][arg0][arg1]...[local0]...
        # FPTR points at arg0, so frame word k lives at FPTR + 3k.
        # Fixed slots are shared by every invocation, which is wrong for
        # recursion -- hence one frame per call.
        self._scan_frame(func.params, func.body)
        nwords = self.frame_words
        nargs = len(func.params)
        # Record parameters so array parameters can be told apart from locals.
        for i, param in enumerate(func.params):
            self.param_addr[param.name] = self.param_slot(i)
        self.in_main = (func.name == "main")

        if self.in_main:
            # LSP lives at a fixed address with no static initializer, so the
            # entry point seeds it.
            self.emit("LDA", "LSP_INIT", comment="A = initial stack pointer")
            self.emit("STA", "LSP")
            self.emit("LDA", "LSP")
            self.emit("STA", "FPTR", comment="FPTR = frame base")
            if nwords:
                self.emit("LDA", "LSP")
                self.emit("ADD", f"#{3 * nwords}")
                self.emit("STA", "LSP", comment="reserve frame words")
        else:
            self._emit_lstack_push()                     # return address
            self.emit("LDA", "FPTR", comment="A = caller FPTR")
            self._emit_push_a()                          # save caller's frame pointer
            self.emit("LDA", "LSP")
            self.emit("STA", "FPTR", comment="FPTR = frame base")
            if nwords:
                self.emit("LDA", "LSP")
                self.emit("ADD", f"#{3 * nwords}")
                self.emit("STA", "LSP", comment="reserve frame words")
            for i in range(nargs):
                # copy the incoming argument from the shared slot into the frame
                self.emit_addr("LDA", self.param_slot(i), comment=f"arg {i}")
                self.emit("STA", "TMP0")
                self.emit("LDA", "FPTR")
                if i:
                    self.emit("ADD", f"#{3 * i}")
                self.emit("STA", "IND")
                self.emit("LDA", "TMP0")
                self.emit("STA", "@IND", comment=f"frame arg {i}")

        self._compile_block(func.body)

        if func.body.statements and func.body.statements[-1].type.value == "ReturnStmt":
            pass  # the ReturnStmt emitted its own epilogue
        elif self.in_main:
            self.emit("HALT", comment="halt")
        else:
            self._emit_frame_epilogue()
            self.emit("RSUB", comment="implicit return")
        self.in_main = False

    def _scan_frame(self, params, block):
        """Assign each parameter and local a word offset from FPTR."""
        self.frame_off = {}
        self.array_locals = set()
        self._frame_next = 0
        for p in params:
            self.frame_off[p.name] = self._frame_next
            self._frame_next += 1
            ann = getattr(p, "type_ann", None)
            if ann is not None and getattr(ann, "kind", None) == "array":
                self.array_locals.add(p.name)
        self._scan_frame_stmts(block.statements)
        self.frame_words = self._frame_next

    def _scan_frame_stmts(self, stmts):
        for s in stmts:
            t = s.type.value
            if t == "LetStmt":
                self.frame_off[s.name] = self._frame_next
                size = 1
                if getattr(s, "array_size", None) is not None:
                    size = (s.array_size.value if isinstance(s.array_size, Literal) else 10)
                    self.array_locals.add(s.name)
                self._frame_next += size
            elif t == "IfStmt":
                self._scan_frame_stmts(s.then_branch.statements)
                if s.else_branch:
                    self._scan_frame_stmts(s.else_branch.statements)
            elif t == "WhileStmt":
                self._scan_frame_stmts(s.body.statements)
            elif t == "ForStmt":
                # the induction variable is a local of this frame
                self.frame_off[s.var] = self._frame_next
                self._frame_next += 1
                self._scan_frame_stmts(s.body.statements)
            elif t == "Block":
                self._scan_frame_stmts(s.statements)

    def _emit_frame_epilogue(self):
        self.emit("STA", "TMP1", comment="save return value across the pops")
        self.emit("LDA", "FPTR", comment="A = FPTR")
        self.emit("STA", "LSP", comment="drop this frame's words")
        self._emit_pop_a()
        self.emit("STA", "FPTR", comment="restore caller's frame pointer")
        self._emit_lstack_pop()                          # restore L
        self.emit("LDA", "TMP1", comment="restore return value")

    def _emit_frame_addr(self, name):
        """IND = FPTR + 3*frame_off[name]."""
        off = 3 * self.frame_off[name]
        self.emit("LDA", "FPTR")
        if off:
            self.emit("ADD", f"#{off}")
        self.emit("STA", "IND")

    def _emit_local_load(self, name):
        self._emit_frame_addr(name)
        self.emit("LDA", "@IND", comment=f"load {name}")

    def _emit_local_store(self, name):
        self.emit("STA", "TMP0", comment=f"value for {name}")
        self._emit_frame_addr(name)
        self.emit("LDA", "TMP0")
        self.emit("STA", "@IND", comment=f"store {name}")

    def _emit_array_base(self, name):
        """A = base address of the array's element words."""
        if name in self.param_addr:
            # array parameter: the caller passed a pointer, copied into the frame
            self._emit_local_load(name)
        else:
            # local array: its words are the frame slot itself
            off = 3 * self.frame_off[name]
            self.emit("LDA", "FPTR")
            if off:
                self.emit("ADD", f"#{off}")

    def _compile_let(self, stmt):
        if getattr(stmt, "array_size", None) is not None:
            # Storage is the frame words reserved by _scan_frame.
            size = stmt.array_size.value if isinstance(stmt.array_size, Literal) else 10
            self.emit_comment(
                f"let {stmt.name} = int[{size}]  @ frame+{3 * self.frame_off[stmt.name]}")
            return
        self._compile_expr(stmt.value)
        self._emit_local_store(stmt.name)

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
        self._emit_local_store(stmt.var)
        loop_label = self.new_label("while")
        end_label = self.new_label("endwhile")
        self.emit_label(loop_label)
        self._emit_local_load(stmt.var)
        self._emit_push_a()
        self._compile_expr(end_expr)
        self.emit("STA", "TMP1", comment="save end")
        self._emit_pop_a()
        self.emit("STA", "TMP0", comment="reload var")
        self.emit("LDA", "TMP0", comment="reload var")
        self.emit("COMP", "TMP1", comment=f"compare {stmt.var} < end")
        self.emit("JGT", end_label, comment="exit if var > end")
        self._compile_block(stmt.body)
        self._emit_local_load(stmt.var)
        self.emit("ADD", "#1", comment="var + 1")
        self._emit_local_store(stmt.var)
        self.emit("J", loop_label, comment="repeat loop")
        self.emit_label(end_label)

    def _compile_return(self, stmt):
        if stmt.value:
            self._compile_expr(stmt.value)
            self.emit("STA", "RETVAL", comment="return value")
        if self.in_main:
            self.emit("HALT", comment="halt - return from main")
        else:
            self._emit_frame_epilogue()
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
            self._emit_array_base(arr_name)
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
        is_local = target_name in getattr(self, "frame_off", {})
        if op == "=":
            self._compile_expr(value)
            if is_local:
                self._emit_local_store(target_name)
            else:
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
            # The target value goes on the value stack so a recursive call in
            # the value expression cannot clobber it.
            if is_local:
                self._emit_local_load(target_name)
            else:
                self.emit_addr("LDA", self.alloc_var(target_name), comment=f"load {target_name}")
            self._emit_push_a()
            self._compile_expr(value)
            self._emit_push_a()
            self._emit_pop_a()
            self.emit("STA", "TMP1", comment="right operand")
            self._emit_pop_a()
            self.emit("STA", "TMP0", comment="left operand")
            if base_op == "+":
                self.emit("ADD", "TMP1", comment=f"{target_name} + right")
            elif base_op == "-":
                self.emit("SUB", "TMP1", comment=f"{target_name} - right")
            elif base_op == "*":
                self.emit("MUL", "TMP1", comment=f"{target_name} * right")
            elif base_op == "/":
                self.emit("DIV", "TMP1", comment=f"{target_name} / right")
            elif base_op == "%":
                # MOD computes A % MOD_ARG, so the divisor is the RIGHT operand
                self.emit("LDA", "TMP1", comment="right operand")
                self.emit("STA", "MOD_ARG", comment="set mod divisor")
                self.emit("LDA", "TMP0", comment="left operand")
                self.emit("JSUB", "MOD", comment=f"{target_name} % right")
            elif base_op == "&":
                self.emit("AND", "TMP1", comment=f"{target_name} & right")
            elif base_op == "|":
                self.emit("OR", "TMP1", comment=f"{target_name} | right")
            elif base_op == "^":
                # XOR computes A ^ XOR_ARG, so the mask is the RIGHT operand
                self.emit("LDA", "TMP1", comment="right operand")
                self.emit("STA", "XOR_ARG", comment="set xor mask")
                self.emit("LDA", "TMP0", comment="left operand")
                self.emit("JSUB", "XOR", comment=f"{target_name} ^ right")
            elif base_op == "<<":
                self.emit("LDA", "TMP1", comment="shift amount")
                self.emit("STA", "SHL_ARG", comment="set shl amount")
                self.emit("LDA", "TMP0", comment="value to shift")
                self.emit("JSUB", "SHL", comment=f"{target_name} << right")
            elif base_op == ">>":
                self.emit("LDA", "TMP1", comment="shift amount")
                self.emit("STA", "SHR_ARG", comment="set shr amount")
                self.emit("LDA", "TMP0", comment="value to shift")
                self.emit("JSUB", "SHR", comment=f"{target_name} >> right")
            if is_local:
                self._emit_local_store(target_name)
            else:
                addr = self.alloc_var(target_name)
                self.emit_addr("STA", addr, comment=f"store {target_name}")

    def _emit_lstack_push(self):
        """Push L onto the return-address stack (one frame per active call)."""
        self.emit("LDA", "LSP", comment="A = stack pointer")
        self.emit("STA", "IND", comment="IND = frame address")
        self.emit("STL", "TMP0", comment="TMP0 = L")
        self.emit("LDA", "TMP0", comment="A = L")
        self.emit("STA", "@IND", comment="push L")
        self.emit("LDA", "LSP", comment="A = LSP")
        self.emit("ADD", "#3")
        self.emit("STA", "LSP", comment="LSP += 3")
        self._emit_stack_guard(overflow=True)

    def _emit_lstack_pop(self):
        """Pop L from the return-address stack, leaving A unchanged."""
        self.emit("STA", "RETVAL", comment="save A across the pop")
        self._emit_stack_guard(overflow=False)
        self.emit("LDA", "LSP", comment="A = LSP")
        self.emit("SUB", "#3")
        self.emit("STA", "LSP", comment="LSP -= 3")
        self.emit("LDA", "LSP", comment="A = frame address")
        self.emit("STA", "IND")
        self.emit("LDA", "@IND", comment="pop L")
        self.emit("STA", "TMP0")
        self.emit("LDL", "TMP0", comment="L = saved return address")
        self.emit("LDA", "RETVAL", comment="restore A")

    def _emit_stack_guard(self, overflow):
        """Trap if the shared stack leaves its fixed region.

        Without this, running off the end writes into unrelated memory and the
        program silently misbehaves.
        """
        if overflow:
            self.emit("LDA", "LSP", comment="A = LSP")
            self.emit("COMP", "LSTACK_LIM")
            self.emit("JGE", "STACK_OVERFLOW", comment="stack full")
        else:
            self.emit("LDA", "LSP", comment="A = LSP")
            self.emit("COMP", "LSTACK_BOT")
            self.emit("JLE", "STACK_UNDERFLOW", comment="stack empty")

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

        The array's element words start at `_emit_array_base(name)`; elements
        are 3-byte words.
        """
        arr_name = expr.left.name
        index_expr = expr.right
        # Use TMP3 (not TMP0/TMP1) so a surrounding expression's operands survive
        self._emit_array_base(arr_name)
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
        if name in getattr(self, "array_locals", set()):
            # an array's value is the address of its element block
            self._emit_array_base(name)
        elif name in getattr(self, "frame_off", {}):
            self._emit_local_load(name)
        else:
            addr = self.alloc_var(name)
            self.emit_addr("LDA", addr, comment=f"load {name}")

    def _emit_push_a(self):
        """Push A onto the value stack (shared with the return-address stack)."""
        self.emit("STA", "TMP0", comment="save A (value being pushed)")
        self.emit("LDA", "LSP")
        self.emit("STA", "IND")
        self.emit("LDA", "TMP0")
        self.emit("STA", "@IND", comment="push A")
        self.emit("LDA", "LSP")
        self.emit("ADD", "#3")
        self.emit("STA", "LSP")
        self._emit_stack_guard(overflow=True)

    def _emit_pop_a(self):
        """Pop A from the value stack."""
        self._emit_stack_guard(overflow=False)
        self.emit("LDA", "LSP")
        self.emit("SUB", "#3")
        self.emit("STA", "LSP")
        self.emit("LDA", "LSP")
        self.emit("STA", "IND")
        self.emit("LDA", "@IND", comment="pop A")

    def _compile_operands(self, left, right):
        """Evaluate `left OP right`, leaving the operands in TMP0/TMP1.

        Operands go through the value stack rather than fixed labels, so a
        recursive call made while evaluating one operand cannot destroy the
        other operand (fixed slots are shared by every invocation).
        """
        self._compile_expr(left)
        self._emit_push_a()
        self._compile_expr(right)
        self._emit_push_a()
        self._emit_pop_a()
        self.emit("STA", "TMP1", comment="right operand")
        self._emit_pop_a()
        self.emit("STA", "TMP0", comment="left operand")

    def _compile_binary(self, expr):
        op = expr.operator
        left = expr.left
        right = expr.right

        if op in ("==", "!=", "<", ">", "<=", ">="):
            self._compile_operands(left, right)
            self.emit("LDA", "TMP0", comment="reload left")
            self.emit("COMP", "TMP1", comment=f"compare {op}")
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

        self._compile_operands(left, right)

        op_map = {
            "+": "ADD",
            "-": "SUB",
            "*": "MUL",
            "/": "DIV",
            "&": "AND",
            "|": "OR",
        }
        if op in op_map:
            self.emit("LDA", "TMP0", comment="reload left")
            self.emit(op_map[op], "TMP1", comment=f"{op} right")
        elif op == "%":
            # left % right = left - (left / right) * right
            self.emit("LDA", "TMP0", comment="left operand")
            self.emit("DIV", "TMP1", comment="left / right")
            self.emit("STA", "TMP2", comment="save quotient")
            self.emit("MUL", "TMP1", comment="quotient * right")
            self.emit("STA", "TMP1", comment="save product")
            self.emit("LDA", "TMP0", comment="reload left")
            self.emit("SUB", "TMP1", comment="left - product = left % right")
        elif op == "^":
            # left ^ right = (left | right) - (left & right)
            self.emit("LDA", "TMP0", comment="reload left")
            self.emit("OR", "TMP1", comment="left | right")
            self.emit("STA", "TMP2", comment="save left|right")
            self.emit("LDA", "TMP0", comment="reload left")
            self.emit("AND", "TMP1", comment="left & right")
            self.emit("STA", "TMP1", comment="save left&right")
            self.emit("LDA", "TMP2", comment="reload left|right")
            self.emit("SUB", "TMP1", comment="(left|right)-(left&right) = left^right")
        elif op == "<<":
            # shift amount is the RIGHT operand; value is the left
            self.emit("LDA", "TMP1", comment="shift amount")
            self.emit("STA", "SHL_ARG", comment="set shl amount")
            self.emit("LDA", "TMP0", comment="value to shift")
            self.emit("JSUB", "SHL", comment=f"{op} right")
        elif op == ">>":
            self.emit("LDA", "TMP1", comment="shift amount")
            self.emit("STA", "SHR_ARG", comment="set shr amount")
            self.emit("LDA", "TMP0", comment="value to shift")
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
        # Both branches leave the result in A, so no temp slot is needed
        # (a slot would be shared across recursive invocations).
        end_label = self.new_label("endtern")
        else_label = self.new_label("ternelse")
        self._compile_expr(expr.condition)
        self.emit("COMP", "#0", comment="condition == 0?")
        self.emit("JEQ", else_label, comment="if false -> else branch")
        self._compile_expr(expr.then_expr)
        self.emit("J", end_label, comment="skip else")
        self.emit_label(else_label)
        self._compile_expr(expr.else_expr)
        self.emit_label(end_label)

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

        # Stack bounds handlers: the value/return stack is a fixed region, so
        # running off either end must report instead of corrupting memory.
        self.emit_label("STACK_OVERFLOW")
        ovf_msg = self.alloc_string("STACK OVERFLOW\n")
        self.emit("LDA", f"#{ovf_msg}")
        self.emit("+JSUB", "65283", comment="print stack overflow")
        self.emit("HALT", comment="halt on stack overflow")
        self.emit_label("STACK_UNDERFLOW")
        unf_msg = self.alloc_string("STACK UNDERFLOW\n")
        self.emit("LDA", f"#{unf_msg}")
        self.emit("+JSUB", "65283", comment="print stack underflow")
        self.emit("HALT", comment="halt on stack underflow")

        # Scratch slots (ZERO, RETVAL, TMP0-4, *_ARG, TERN_RESULT, IND, LSP,
        # FPTR) are NOT defined here: they live at the fixed addresses in
        # SLOT_ADDRS so every object file agrees on them.
        self.emit_label("LSTACK_BOT")
        self.emit_directive("WORD", str(self.LSTACK_BASE),
                            comment="stack lower bound")
        self.emit_label("LSTACK_LIM")
        self.emit_directive("WORD", str(self.LSTACK_BASE + 3 * self.LSTACK_FRAMES),
                            comment="stack upper bound (exclusive)")
        self.emit_label("LSP_INIT")
        self.emit_directive("WORD", str(self.LSTACK_BASE),
                            comment="initial stack pointer")
        # The stack itself lives in the fixed region [LSTACK_BASE, LSTACK_LIM);
        # nothing else is placed there (slots at 0xF000, SVC page at 0xFF00).
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
