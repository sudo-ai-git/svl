#!/usr/bin/env python3
"""
SIC/XE Assembler and Simulator

Two-pass assembler producing SIC/XE object code (H, T, E records),
plus a simulator that executes the object code with:
  - Linkage Register (L) tracking on JSUB/RSUB
  - Indexed addressing (X bit) with TA = address + (X)
  - Full instruction trace
"""

import sys
import json
from pathlib import Path

# ═════════════════════════════════════════════════════════════════════════════
# INSTRUCTION SET (SIC/XE)
# Format: opcode (hex), format (3 or 4)
# ═════════════════════════════════════════════════════════════════════════════

OPTAB = {
    # SIC instructions (format 3)
    "LDA":  ("00", 3), "LDX":  ("04", 3), "LDB":  ("68", 3), "LDS":  ("6C", 3),
    "LDT":  ("74", 3), "LDF":  ("70", 3), "STA":  ("0C", 3), "STX":  ("10", 3),
    "STB":  ("78", 3), "STS":  ("7C", 3), "STT":  ("84", 3), "STF":  ("80", 3),
    "ADD":  ("18", 3), "ADDF":  ("58", 3), "SUB":  ("1C", 3), "SUBF":  ("5C", 3),
    "MUL":  ("20", 3), "MULF":  ("60", 3), "DIV":  ("24", 3), "DIVF":  ("64", 3),
    "COMP":  ("28", 3), "COMPF":  ("88", 3), "TIX":  ("2C", 3),
    "J":  ("3C", 3), "JLT":  ("38", 3), "JEQ":  ("30", 3), "JGT":  ("34", 3),
    "JLE":  ("40", 3), "JNE":  ("44", 3), "JGE":  ("48", 3),
    "JSUB":  ("4B", 3), "RSUB":  ("4F", 3),
    "AND":  ("40", 3), "OR":  ("44", 3), "SHIFTL":  ("A8", 3), "SHIFTR":  ("AC", 3),
    "SVC":  ("B0", 3), "TD":  ("E0", 3), "RD":  ("D8", 3), "WD":  ("DC", 3),
    # SIC/XE extensions (format 4 with +)
    "+LDA":  ("00", 4), "+LDX":  ("04", 4), "+STA":  ("0C", 4), "+STX":  ("10", 4),
    "+ADD":  ("18", 4), "+SUB":  ("1C", 4), "+MUL":  ("20", 4), "+DIV":  ("24", 4),
    "+COMP":  ("28", 4), "+J":  ("3C", 4), "+JSUB":  ("4B", 4), "+RSUB":  ("4F", 4),
    "+AND":  ("40", 4), "+OR":  ("44", 4),
}

# Registers: A, X, L, B, S, T, F, PC, SW
REGISTERS = {"A": 0, "X": 1, "L": 2, "B": 3, "S": 4, "T": 5, "F": 6, "PC": 8, "SW": 9}


# ═════════════════════════════════════════════════════════════════════════════
# SYMBOL TABLE ENTRY
# ═════════════════════════════════════════════════════════════════════════════

class SymTabEntry:
    def __init__(self, address, relocatable=True):
        self.address = address
        self.relocatable = relocatable


# ═════════════════════════════════════════════════════════════════════════════
# TWO-PASS ASSEMBLER
# ═════════════════════════════════════════════════════════════════════════════

class Assembler:
    def __init__(self, source_lines):
        self.source = source_lines          # list of (label, opcode, operand, comment)
        self.symtab = {}                    # symbol -> SymTabEntry
        self.lit_tab = {}                   # literal -> address
        self.lit_pool = []                  # list of literal values
        self.locctr = 0
        self.start_address = 0
        self.program_name = ""
        self.program_length = 0
        self.object_code = []               # list of (address, object_code_hex, is_format4)
        self.errors = []
        self.line_info = []                 # (source_line_num, locctr, label, opcode, operand, obj_code)

    def _error(self, msg, line_num=None):
        where = f"line {line_num}" if line_num is not None else ""
        self.errors.append(f"{where}: {msg}")

    def assemble(self):
        """Two-pass assembly. Returns (success, object_records)."""
        self._pass1()
        if self.errors:
            return False, None
        self._pass2()
        if self.errors:
            return False, None
        records = self._emit_object_records()
        return True, records

    # ---------------------------------------------------------------- pass 1
    def _pass1(self):
        i = 0
        while i < len(self.source):
            line_num, label, opcode, operand, comment = self.source[i]

            # START directive
            if opcode.upper() == "START":
                self.program_name = (label or "NONAME")[:8]
                self.start_address = int(operand, 16) if operand else 0
                self.locctr = self.start_address
                self.line_info.append((line_num, self.locctr, label, opcode, operand, ""))
                i += 1
                continue

            # END directive
            if opcode.upper() == "END":
                self.program_length = self.locctr - self.start_address
                self.line_info.append((line_num, self.locctr, label, opcode, operand, ""))
                break

            # Register label in symbol table
            if label:
                if label in self.symtab:
                    self._error(f"Duplicate symbol '{label}'", line_num)
                else:
                    self.symtab[label] = SymTabEntry(self.locctr)

            # Determine instruction size
            size = self._instruction_size(opcode, operand)
            if size is None:
                # Directive: reserve memory
                if opcode.upper() in ("BYTE", "WORD", "RESB", "RESW"):
                    size = self._directive_size(opcode, operand, line_num)
                    if size is None:
                        i += 1
                        continue
                else:
                    self._error(f"Unknown opcode or directive '{opcode}'", line_num)
                    i += 1
                    continue

            self.line_info.append((line_num, self.locctr, label, opcode, operand, ""))
            self.locctr += size
            i += 1

    def _instruction_size(self, opcode, operand):
        """Return instruction size in bytes, or None if it's a directive."""
        op = opcode.upper()

        # Format 4 with explicit +
        if op.startswith("+"):
            base = op[1:]
            if base in OPTAB:
                return OPTAB[base][1]
            return None

        # RSUB is always format 3 (no operand)
        if op == "RSUB":
            return 3

        if op in OPTAB:
            fmt = OPTAB[op][1]
            # Format 3/4 decision: if operand has explicit format marker (not in SIC/XE,
            # but we treat any instruction as format 3 unless + prefix). For SIC/XE,
            # format 4 is only with +. So format 3 by default.
            return fmt

        return None

    def _directive_size(self, opcode, operand, line_num):
        op = opcode.upper()
        if op == "BYTE":
            if operand.startswith("C'") and operand.endswith("'"):
                return len(operand) - 3  # characters between C' and '
            if operand.startswith("X'") and operand.endswith("'"):
                return (len(operand) - 3 + 1) // 2  # hex bytes
            self._error(f"Invalid BYTE constant: {operand}", line_num)
            return None
        if op == "WORD":
            return 3
        if op == "RESB":
            return int(operand)
        if op == "RESW":
            return 3 * int(operand)
        self._error(f"Unknown directive '{opcode}'", line_num)
        return None

    # ---------------------------------------------------------------- pass 2
    def _pass2(self):
        for line_num, locctr, label, opcode, operand, _ in self.line_info:
            op = opcode.upper()
            obj_code = ""
            is_format4 = False

            if op == "START":
                continue
            if op == "END":
                break
            if op in ("BYTE", "WORD", "RESB", "RESW"):
                obj_code = self._directive_object(op, operand, line_num)
                self.object_code.append((locctr, obj_code, False))
                continue

            # Determine format and flags
            format4 = False
            if op.startswith("+"):
                format4 = True
                op = op[1:]

            n_i = "10"  # simple addressing by default
            x = "0"
            b_p = "00"
            e = "1" if format4 else "0"
            target_address = 0
            disp = 0

            # Parse addressing mode flags from operand
            operand_str = operand or ""
            indirect = operand_str.startswith("@")
            immediate = operand_str.startswith("#")
            indexed = ",X" in operand_str

            # Clean operand
            clean = operand_str.lstrip("@#").replace(",X", "").strip()

            if indirect:
                n_i = "01"
            elif immediate:
                n_i = "01"  # immediate uses n=0,i=1
            else:
                n_i = "10"

            x = "1" if indexed else "0"

            # Resolve target address
            if op == "RSUB":
                # RSUB: no operand, format 3, opcode only
                obj_code = f"{OPTAB['RSUB'][0]}0000"
                self.object_code.append((locctr, obj_code, False))
                continue

            if clean.isdigit():
                target_address = int(clean)
            elif clean.startswith("="):  # literal
                # Literal: create a literal pool entry
                lit_val = clean
                if lit_val not in self.lit_tab:
                    self.lit_tab[lit_val] = None  # assigned later (simplified: use current locctr+size)
                    self.lit_pool.append(lit_val)
                # For simplicity, place literal right after current instruction
                target_address = self.locctr  # will be back-patched; simplified approach
            elif clean in self.symtab:
                target_address = self.symtab[clean].address
            else:
                self._error(f"Undefined symbol '{clean}'", line_num)
                continue

            # Compute displacement (format 3) or full address (format 4)
            target_address_value = target_address
            if format4:
                # For format 4, address is 20 bits
                addr_field = target_address_value & 0xFFFFF
                b_p = "00"
            else:
                # Format 3: PC-relative or base-relative
                # locctr comes from the line_info tuple (current instruction address)
                pc_after = locctr + 3
                diff = target_address - pc_after
                # PC-relative: p=1, b=0. Base-relative: b=1, p=0.
                if -2048 <= diff <= 2047:
                    b_p = "01"  # PC-relative (b=0, p=1)
                    disp = diff & 0xFFF
                else:
                    # Base-relative with base=0 for simplicity
                    b_p = "10"  # base-relative (b=1, p=0)
                    disp = target_address & 0xFFF
                    if target_address > 4095:
                        self._error(f"Address {target_address} out of range for format 3 at line {line_num}", line_num)
                        continue

            # Assemble object code
            opcode_hex = OPTAB[op][0]
            opcode_byte = int(opcode_hex, 16)

            # Add n,i bits to opcode byte.  Most optab values (LDA=00, STA=0C, etc.)
            # have 00 in the bottom 2 bits, so OR'ing ni works.  JSUB (4B) and RSUB (4F)
            # already have 11 in the bottom 2 bits — those are part of the opcode, not
            # addressing mode — so use them as-is.
            ni_val = int(n_i, 2)
            if op in ("JSUB", "RSUB"):
                opcode_byte = opcode_byte  # already complete
            else:
                opcode_byte = opcode_byte | ni_val

            # Byte 1: opcode (6 bits) + n(1) + i(1) = already combined above
            # Byte 2: x(1) + b(1) + p(1) + e(1) + high 4 bits of address/disp
            # Byte 3-4: low 8 bits of address/disp

            if format4:
                # Format 4: 4 bytes total
                # Byte1 = opcode(6) + n(1) + i(1)
                # Byte2 = x(1) + b(1) + p(1) + e(1) + address[19:16]
                # Byte3 = address[15:8]
                # Byte4 = address[7:0]
                byte1 = opcode_byte
                xbe_val = int(x + b_p + e, 2)
                addr20 = target_address_value & 0xFFFFF
                byte2 = (xbe_val << 4) | ((addr20 >> 16) & 0xF)
                byte3 = (addr20 >> 8) & 0xFF
                byte4 = addr20 & 0xFF
                obj_code = f"{byte1:02X}{byte2:02X}{byte3:02X}{byte4:02X}"
                is_format4 = True
            else:
                # 3 bytes: op(6)+ni(2) | x b p e | disp(12 bits)
                byte1 = opcode_byte
                xbpe_val = int(x + b_p + e, 2)
                disp12 = disp & 0xFFF
                byte2 = (xbpe_val << 4) | ((disp12 >> 8) & 0xF)
                byte3 = disp12 & 0xFF
                obj_code = f"{byte1:02X}{byte2:02X}{byte3:02X}"

            self.object_code.append((locctr, obj_code, is_format4))

    def _directive_object(self, op, operand, line_num):
        op = op.upper()
        if op == "BYTE":
            if operand.startswith("C'") and operand.endswith("'"):
                chars = operand[2:-1]
                return "".join(f"{ord(c):02X}" for c in chars)
            if operand.startswith("X'") and operand.endswith("'"):
                return operand[2:-1].upper()
            return ""
        if op == "WORD":
            val = int(operand)
            return f"{val & 0xFFFFFF:06X}"
        if op in ("RESB", "RESW"):
            return ""
        return ""

    # ---------------------------------------------------------------- object records
    def _emit_object_records(self):
        """Generate H, T, E records in SIC/XE object format."""
        if not self.program_name:
            self.program_name = "NONAME"

        # H record: H^name^start_address^program_length
        h_record = f"H^{self.program_name:<6}^{self.start_address:06X}^{self.program_length:06X}"

        # T records: group contiguous object code into text records
        # Filter out directives with no object code (RESB/RESW create gaps)
        code_entries = [(addr, code) for addr, code, _ in self.object_code if code]
        t_records = []
        if code_entries:
            current_start = code_entries[0][0]
            current_bytes = []
            current_end = current_start

            for addr, code in code_entries:
                # If not contiguous with current T record, flush it
                if addr != current_end or len(current_bytes) + len(code) // 2 > 60:
                    if current_bytes:
                        t_records.append(
                            f"T^{current_start:06X}^{len(current_bytes):02X}^{''.join(current_bytes)}"
                        )
                    current_start = addr
                    current_bytes = []
                current_bytes.append(code)
                current_end = addr + len(code) // 2

            if current_bytes:
                t_records.append(
                    f"T^{current_start:06X}^{len(current_bytes):02X}^{''.join(current_bytes)}"
                )

        # E record: E^start_address
        e_record = f"E^{self.start_address:06X}"

        return {"H": h_record, "T": t_records, "E": e_record,
                "start": self.start_address, "length": self.program_length}


# ═════════════════════════════════════════════════════════════════════════════
# SIMULATOR
# ═════════════════════════════════════════════════════════════════════════════

class Simulator:
    def __init__(self, memory_size=0x100000):  # 1 MB addressable
        self.memory = [0] * memory_size       # byte-addressable memory
        self.regs = {r: 0 for r in REGISTERS}  # A, X, L, B, S, T, F, PC, SW
        self.pc = 0
        self.running = False
        self.trace = []                       # execution trace lines
        self.max_steps = 100000

    def load_object_code(self, code_entries, start_address):
        """code_entries: list of (address, hex_string, is_format4)."""
        self.regs["PC"] = start_address
        self.pc = start_address
        for addr, code, _is_fmt4 in code_entries:
            if not code:
                continue
            for i in range(0, len(code), 2):
                byte = int(code[i:i+2], 16)
                self.memory[addr + i // 2] = byte

    def _read_word(self, addr):
        """Read 3 bytes (24-bit word) from addr."""
        return (self.memory[addr] << 16) | (self.memory[addr + 1] << 8) | self.memory[addr + 2]

    def _write_word(self, addr, value):
        self.memory[addr] = (value >> 16) & 0xFF
        self.memory[addr + 1] = (value >> 8) & 0xFF
        self.memory[addr + 2] = value & 0xFF

    def _fetch_instruction(self):
        """Fetch instruction at PC, return (byte1, opcode, format, ni, x, b, p, e, disp_or_addr, new_pc)."""
        pc = self.pc
        byte1 = self.memory[pc]
        opcode6 = (byte1 >> 2) & 0x3F   # top 6 bits
        ni = byte1 & 0x03                # bottom 2 bits

        # Check for format 4: bit 8 of byte2 (e bit)
        byte2 = self.memory[pc + 1]
        x = (byte2 >> 7) & 1
        b = (byte2 >> 6) & 1
        p = (byte2 >> 5) & 1
        e = (byte2 >> 4) & 1

        if e:
            # Format 4: 4 bytes total
            addr20 = ((byte2 & 0x0F) << 16) | (self.memory[pc + 2] << 8) | self.memory[pc + 3]
            return byte1, opcode6, 4, ni, x, b, p, e, addr20, pc + 4
        else:
            # Format 3: 3 bytes
            disp12 = ((byte2 & 0x0F) << 8) | self.memory[pc + 2]
            return byte1, opcode6, 3, ni, x, b, p, e, disp12, pc + 3

    def _compute_target_address(self, ni, x, b, p, e, disp, pc_after_fetch):
        """Compute TA considering n/i, x, b, p, e."""
        # Indirect/immediate don't change TA calculation itself; they change how the value at TA is used.
        ta = 0
        if e:
            ta = disp  # full 20-bit address
        elif b:
            ta = self.regs["B"] + disp
        elif p:
            ta = pc_after_fetch + self._sign_extend(disp, 12)
        else:
            ta = disp  # base=0, direct

        # Indexed addressing: TA = address + (X)
        if x:
            ta = ta + self.regs["X"]

        return ta & 0xFFFFF

    def _sign_extend(self, val, bits):
        sign_bit = 1 << (bits - 1)
        return (val & (sign_bit - 1)) - (val & sign_bit)

    def _read_target_value(self, ta, ni):
        """Read value at TA, applying n/i addressing mode."""
        # n=1,i=1 (simple): value at TA
        # n=1,i=0 (indirect): value at (value at TA)  -- memory indirect
        # n=0,i=1 (immediate): the value IS TA itself
        # n=0,i=0: (SIC/XE: SIC mode, treat as simple)
        if ni == 0b01:  # immediate
            return ta
        elif ni == 0b10:  # simple
            return self._read_word(ta)
        elif ni == 0b01:  # indirect (same as immediate in this simplified model? No)
            # Indirect: read word at TA, that word is the address, read word at that address
            addr = self._read_word(ta)
            return self._read_word(addr)
        else:
            return self._read_word(ta)

    def _execute(self, byte1, opcode6, fmt, ni, x, b, p, e, disp, new_pc):
        """Execute an instruction. Returns (next_pc, trace_line, should_stop)."""
        # Map opcode to mnemonic for trace
        mnemonic = self._opcode_to_mnemonic(opcode6, fmt, byte1)
        trace_line = f"  PC={self.pc:06X} {mnemonic:<8} "

        # Special-case JSUB and RSUB using the full byte1 value,
        # since JSUB (0x4B) and JGE (0x48) share the same top 6 bits.
        if byte1 == 0x4B:  # JSUB
            return_address = new_pc  # PC after fetching JSUB
            self.regs["L"] = return_address
            ta = self._compute_target_address(ni, x, b, p, e, disp, new_pc)
            trace_line += (f"JSUB: L <- {return_address:06X} (return addr), "
                          f"PC <- {ta:06X} (target)")
            if x:
                trace_line += f" [indexed: TA = base + X = {ta:06X}]"
            self.regs["PC"] = ta
            self.pc = ta
            return ta, trace_line, False

        if byte1 == 0x4F:  # RSUB
            trace_line += f"RSUB: PC <- L = {self.regs['L']:06X}"
            self.regs["PC"] = self.regs["L"]
            self.pc = self.regs["L"]
            return self.regs["L"], trace_line, False

        # For other instructions, just compute TA and read value for trace
        ta = self._compute_target_address(ni, x, b, p, e, disp, new_pc)

        if mnemonic in ("LDA", "LDX", "LDB", "LDS", "LDT", "LDF"):
            reg_name = mnemonic[2]  # LDA->A, LDX->X, LDB->B, LDS->S, LDT->T, LDF->F
            val = self._read_target_value(ta, ni)
            self.regs[reg_name] = val & 0xFFFFFF
            idx_note = f" [X={self.regs['X']:06X}]" if x else ""
            trace_line += f"{reg_name} <- mem[{ta:06X}] = {val:06X}{idx_note}"
            self.pc = new_pc
            return new_pc, trace_line, False

        if mnemonic in ("STA", "STX", "STB", "STS", "STT", "STF"):
            reg_name = mnemonic[2]
            val = self.regs[reg_name]
            self._write_word(ta, val)
            idx_note = f" [X={self.regs['X']:06X}]" if x else ""
            trace_line += f"mem[{ta:06X}] <- {reg_name} = {val:06X}{idx_note}"
            self.pc = new_pc
            return new_pc, trace_line, False

        if mnemonic == "ADD":
            val = self._read_target_value(ta, ni)
            self.regs["A"] = (self.regs["A"] + val) & 0xFFFFFF
            trace_line += f"A <- A + mem[{ta:06X}] = {self.regs['A']:06X}"
        elif mnemonic == "SUB":
            val = self._read_target_value(ta, ni)
            self.regs["A"] = (self.regs["A"] - val) & 0xFFFFFF
            trace_line += f"A <- A - mem[{ta:06X}] = {self.regs['A']:06X}"
        elif mnemonic == "MUL":
            val = self._read_target_value(ta, ni)
            self.regs["A"] = (self.regs["A"] * val) & 0xFFFFFF
            trace_line += f"A <- A * mem[{ta:06X}] = {self.regs['A']:06X}"
        elif mnemonic == "DIV":
            val = self._read_target_value(ta, ni)
            if val == 0:
                trace_line += f"DIV by zero at {ta:06X}"
                return new_pc, trace_line, True
            self.regs["A"] = (self.regs["A"] // val) & 0xFFFFFF
            trace_line += f"A <- A / mem[{ta:06X}] = {self.regs['A']:06X}"
        elif mnemonic == "COMP":
            val = self._read_target_value(ta, ni)
            a = self.regs["A"]
            if a == val:
                self.regs["SW"] = 0  # equal
                trace_line += f"COMP: A({a:06X}) == mem[{ta:06X}], SW=EQ"
            elif a < val:
                self.regs["SW"] = 1  # less
                trace_line += f"COMP: A({a:06X}) < mem[{ta:06X}], SW=LT"
            else:
                self.regs["SW"] = 2  # greater
                trace_line += f"COMP: A({a:06X}) > mem[{ta:06X}], SW=GT"
        elif mnemonic == "J":
            self.pc = ta
            trace_line += f"J -> {ta:06X}"
            return ta, trace_line, False
        elif mnemonic == "JLT":
            if self.regs["SW"] == 1:
                self.pc = ta
                trace_line += f"JLT taken -> {ta:06X}"
                return ta, trace_line, False
            trace_line += "JLT not taken"
        elif mnemonic == "JEQ":
            if self.regs["SW"] == 0:
                self.pc = ta
                trace_line += f"JEQ taken -> {ta:06X}"
                return ta, trace_line, False
            trace_line += "JEQ not taken"
        elif mnemonic == "JGT":
            if self.regs["SW"] == 2:
                self.pc = ta
                trace_line += f"JGT taken -> {ta:06X}"
                return ta, trace_line, False
            trace_line += "JGT not taken"
        elif mnemonic == "TIX":
            val = self.regs["X"]
            self.regs["X"] = (self.regs["X"] + 1) & 0xFFFFFF
            cmp_val = self._read_target_value(ta, ni)
            if self.regs["X"] < cmp_val:
                self.regs["SW"] = 1
            elif self.regs["X"] == cmp_val:
                self.regs["SW"] = 0
            else:
                self.regs["SW"] = 2
            trace_line += f"X <- {self.regs['X']:06X}, compare with {cmp_val:06X}"
        else:
            trace_line += f"(opcode {opcode6:02X} not implemented in simulator)"

        self.pc = new_pc
        return new_pc, trace_line, False

    def _opcode_to_mnemonic(self, opcode6, fmt, byte1=None):
        # JSUB (0x4B) and JGE (0x48) share opcode6=0x12; use full byte1 to disambiguate
        if byte1 == 0x4B:
            return "JSUB"
        if byte1 == 0x4F:
            return "RSUB"
        reverse = {}
        for mnem, (hexstr, f) in OPTAB.items():
            if f == fmt:
                key = int(hexstr, 16) >> 2  # top 6 bits = opcode6
                if key not in reverse:
                    reverse[key] = mnem.lstrip("+")
        return reverse.get(opcode6, f"OP{opcode6:02X}")

    def run(self):
        self.running = True
        self.trace = []
        steps = 0
        while self.running and steps < self.max_steps:
            if self.pc >= len(self.memory):
                self.trace.append(f"  PC={self.pc:06X} out of memory bounds")
                break
            byte1, opcode6, fmt, ni, x, b, p, e, disp, new_pc = self._fetch_instruction()
            next_pc, trace_line, stop = self._execute(byte1, opcode6, fmt, ni, x, b, p, e, disp, new_pc)
            self.trace.append(trace_line)
            steps += 1
            if stop:
                break
        self.running = False
        return self.trace


# ═════════════════════════════════════════════════════════════════════════════
# SOURCE PARSER
# ═════════════════════════════════════════════════════════════════════════════

def parse_source(text):
    """Parse assembly source text into (line_num, label, opcode, operand, comment) tuples."""
    lines = []
    for idx, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("."):
            continue
        # Remove comment
        if "." in line:
            # Only treat '.' as comment start if preceded by space or at start
            parts = line.split(".", 1)
            line = parts[0].strip()
            comment = parts[1].strip() if len(parts) > 1 else ""
        else:
            comment = ""

        # Split into label, opcode, operand
        tokens = line.split()
        if not tokens:
            continue

        # Heuristic: if first token ends with ':' or is followed by an opcode-like token
        label = ""
        opcode = ""
        operand = ""

        if len(tokens) == 1:
            opcode = tokens[0]
        elif len(tokens) == 2:
            # Could be "label opcode" or "opcode operand"
            if tokens[0].upper() in OPTAB or tokens[0].upper() in ("START", "END", "BYTE", "WORD", "RESB", "RESW", "BASE", "NOBASE"):
                opcode = tokens[0]
                operand = tokens[1]
            else:
                label = tokens[0]
                opcode = tokens[1]
        elif len(tokens) >= 3:
            label = tokens[0]
            opcode = tokens[1]
            operand = " ".join(tokens[2:])

        lines.append((idx, label, opcode, operand, comment))
    return lines


# ═════════════════════════════════════════════════════════════════════════════
# DEMO PROGRAM AND MAIN
# ═════════════════════════════════════════════════════════════════════════════

DEMO_SOURCE = """        START  1000
MAIN     JSUB   RDREC
         LDA    LENGTH
         STA    LENSAVE
LOOP     LDA    ZERO
         COMP   ZERO
         JEQ    ENDCOPY
         SUB    LENGTH
         STA    LENGTH
         J      LOOP
ENDCOPY  RSUB
LENGTH   WORD   3
LENSAVE  RESW   1
ZERO     WORD   0
RDREC    LDX    ZERO
         LDA    BUFFER,X
         STA    LENSAVE
         RSUB
BUFFER   WORD   10
         WORD   20
         WORD   30
         END    MAIN
"""


def main():
    print("=" * 70)
    print("SIC/XE ASSEMBLER AND SIMULATOR")
    print("=" * 70)

    # Parse source
    source = parse_source(DEMO_SOURCE)
    print(f"\nParsed {len(source)} source statements")

    # Assemble
    asm = Assembler(source)
    success, records = asm.assemble()

    if not success:
        print("ASSEMBLY FAILED:")
        for err in asm.errors:
            print(f"  {err}")
        return 1

    # Print symbol table
    print("\n--- Symbol Table ---")
    for sym, entry in sorted(asm.symtab.items()):
        print(f"  {sym:<8} = {entry.address:06X}")

    # Print object code
    print("\n--- Object Code (Pass 2) ---")
    for addr, code, is_fmt4 in asm.object_code:
        fmt_tag = "F4" if is_fmt4 else "F3"
        print(f"  {addr:06X}: {code:<12} [{fmt_tag}]")

    # Print object records
    print("\n--- Object Records ---")
    print(f"  H: {records['H']}")
    for t in records["T"]:
        print(f"  T: {t}")
    print(f"  E: {records['E']}")

    # Simulate
    print("\n--- Simulation Trace ---")
    sim = Simulator()
    sim.load_object_code(asm.object_code, records["start"])
    trace = sim.run()

    for line in trace:
        print(line)

    print("\n--- Final Register State ---")
    for reg in ["A", "X", "L", "B", "S", "T", "F", "PC", "SW"]:
        print(f"  {reg} = {sim.regs[reg]:06X}")

    print("\n" + "=" * 70)
    print("VERIFICATION: JSUB sets L = return address; RSUB restores PC from L")
    print("              Indexed addressing: TA = address + (X)")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
