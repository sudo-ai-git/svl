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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svl.gate231 import compute_checksums as gate231_compute_checksums
from qec_memory import QECMemory

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
    "JLE":  ("50", 3), "JNE":  ("54", 3), "JGE":  ("48", 3),
    "JSUB":  ("4B", 3), "RSUB":  ("4F", 3),
    "AND":  ("40", 3), "OR":  ("44", 3), "SHIFTL":  ("A8", 3), "SHIFTR":  ("AC", 3),
    "SVC":  ("B0", 3), "TD":  ("E0", 3), "RD":  ("D8", 3), "WD":  ("DC", 3),
    "STL":  ("90", 3), "LDL":  ("94", 3),  # store/load L register (for return-addr save/restore)
    # SIC/XE extensions (format 4 with +)
    "+LDA":  ("00", 4), "+LDX":  ("04", 4), "+STA":  ("0C", 4), "+STX":  ("10", 4),
    "+ADD":  ("18", 4), "+SUB":  ("1C", 4), "+MUL":  ("20", 4), "+DIV":  ("24", 4),
    "+COMP":  ("28", 4), "+J":  ("3C", 4), "+JSUB":  ("4B", 4), "+RSUB":  ("4F", 4),
    "+AND":  ("40", 4), "+OR":  ("44", 4),
    "HALT":  ("FF", 1),  # halt instruction - simulator stops on this opcode
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
        self.undefined_symbols = {}         # symbol -> [(addr, offset_within_instr), ...]
        self.lit_tab = {}                   # literal -> address
        self.lit_pool = []                  # list of literal values
        self.locctr = 0
        self.start_address = 0
        self.entry_symbol = None   # entry point symbol from END directive
        self.program_name = ""
        self.program_length = 0
        self.object_code = []               # list of (address, object_code_hex, is_format4)
        self.errors = []
        self.line_info = []                 # (source_line_num, locctr, label, opcode, operand, obj_code)

    def _error(self, msg, line_num=None):
        where = f"line {line_num}" if line_num is not None else ""
        self.errors.append(f"{where}: {msg}")

    def assemble(self, write_symbol_file_path: str = None):
        """Two-pass assembly. Returns (success, object_records).

        If write_symbol_file_path is given, also writes a .sym sidecar
        file for linker consumption.
        """
        self._pass1()
        if self.errors:
            return False, None
        self._pass2()
        if self.errors:
            return False, None
        records = self._emit_object_records()
        if write_symbol_file_path:
            self.write_symbol_file(write_symbol_file_path)
        return True, records

    def write_symbol_file(self, path: str):
        """Write symbol table sidecar file for linker consumption.
        
        Format (one symbol per line):
          D <symbol> <address>    - defined symbol at absolute address
          U <symbol> <ref_addr>   - undefined symbol referenced at ref_addr
        """
        lines = []
        for sym, entry in sorted(self.symtab.items()):
            lines.append(f"D {sym} {entry.address:06X}")
        for sym, refs in sorted(self.undefined_symbols.items()):
            for ref_addr, _offset in refs:
                lines.append(f"U {sym} {ref_addr:06X}")
        Path(path).write_text("\n".join(lines) + "\n")

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
                self.entry_symbol = operand.strip() if operand else None
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
            if op in OPTAB:
                return OPTAB[op][1]  # +JSUB -> format 4, etc.
            base = op[1:]
            if base in OPTAB:
                return 4  # format 4 instructions are always 4 bytes
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

            # Parse SYMBOL+OFFSET or SYMBOL-OFFSET expressions
            offset = 0
            if "+" in clean:
                parts = clean.split("+", 1)
                clean = parts[0]
                offset = int(parts[1])
            elif "-" in clean and not clean.startswith("-"):
                parts = clean.split("-", 1)
                clean = parts[0]
                offset = -int(parts[1])

            if indirect:
                n_i = "10"   # indirect: n=1, i=0
            elif immediate:
                n_i = "01"   # immediate: n=0, i=1
            else:
                n_i = "11"   # simple: n=1, i=1

            x = "1" if indexed else "0"

            # Resolve target address
            if op == "RSUB":
                # RSUB: no operand, format 3, opcode only
                obj_code = f"{OPTAB['RSUB'][0]}0000"
                self.object_code.append((locctr, obj_code, False))
                continue

            if not format4 and op in OPTAB and OPTAB[op][1] == 1:
                # Format 1: single-byte opcode, no operand (e.g. HALT)
                obj_code = f"{OPTAB[op][0]}00"
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
                target_address = self.symtab[clean].address + offset
            else:
                # Record undefined symbol for linker resolution
                self.undefined_symbols.setdefault(clean, []).append(
                    (locctr, offset)  # address, offset within instruction
                )
                target_address = 0  # placeholder, will be relocated by linker
                # Don't error - let the linker resolve it

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
            if op in ("JSUB", "RSUB", "JGE"):
                opcode_byte = opcode_byte  # already complete (jump instructions don't use ni bits)
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
        """Generate H, T, E records in SIC/XE object format.

        Each T record is stamped with a 231-gate three-channel checksum
        (SUM/LINEAR/ROLLING mod 231) over its raw data bytes, appended as
        ':G:sum:lin:rol'.  This makes the object code tamper-evident: the
        simulator verifies the checksums before executing any instruction.
        """
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
                        hex_data = ''.join(current_bytes)
                        byte_count = len(hex_data) // 2
                        s, l, r = gate231_compute_checksums(bytes.fromhex(hex_data))
                        t_records.append(
                            f"T^{current_start:06X}^{byte_count:02X}^{hex_data}"
                            f":G:{s}:{l}:{r}"
                        )
                    current_start = addr
                    current_bytes = []
                current_bytes.append(code)
                current_end = addr + len(code) // 2

            if current_bytes:
                hex_data = ''.join(current_bytes)
                byte_count = len(hex_data) // 2
                s, l, r = gate231_compute_checksums(bytes.fromhex(hex_data))
                t_records.append(
                    f"T^{current_start:06X}^{byte_count:02X}^{hex_data}"
                    f":G:{s}:{l}:{r}"
                )

        # E record: use entry symbol address if available, else start_address
        entry_addr = self.start_address
        if self.entry_symbol:
            sym = self.symtab.get(self.entry_symbol)
            if sym is None:
                # Try case-insensitive match
                for name, entry in self.symtab.items():
                    if name.upper() == self.entry_symbol.upper():
                        sym = entry
                        break
            if sym is not None:
                entry_addr = sym.address
        e_record = f"E^{entry_addr:06X}"

        return {"H": h_record, "T": t_records, "E": e_record,
                "start": self.start_address, "length": self.program_length}


# ═════════════════════════════════════════════════════════════════════════════
# SIMULATOR
# ═════════════════════════════════════════════════════════════════════════════

class Simulator:
    def __init__(self, memory_size=0x10000):  # 64 KiB default (QEC memory is expensive)
        self.memory = QECMemory(size_bytes=memory_size)  # QEC-protected byte-addressable memory
        self.regs = {r: 0 for r in REGISTERS}  # A, X, L, B, S, T, F, PC, SW
        self.pc = 0
        self.running = False
        self.trace = []                       # execution trace lines
        self.max_steps = 100000
        self._open_files = {}               # fd -> file object for SVC I/O

    def load_object_code(self, code_entries, start_address):
        """code_entries: list of (address, hex_string, is_format4)."""
        self.regs["PC"] = start_address
        self.pc = start_address
        for addr, code, _is_fmt4 in code_entries:
            if not code:
                continue
            for i in range(0, len(code), 2):
                byte = int(code[i:i+2], 16)
                self.memory.write_byte(addr + i // 2, byte)

    def verify_and_load_records(self, records):
        """Load object records with 231-gate tamper verification.

        Parses H, T, E records.  For each T record, extracts the embedded
        ':G:sum:lin:rol' 231-gate checksum, recomputes it over the data
        bytes, and refuses to load if any channel mismatches.

        Returns the start address from the H record.
        Raises ValueError if any T record fails the 231-gate check.
        """
        import re

        # --- Parse H record for start address ---
        h_rec = records["H"]
        m = re.match(r"H\^(.{6})\^([0-9A-Fa-f]{6})\^([0-9A-Fa-f]{6})$", h_rec)
        if not m:
            raise ValueError(f"Malformed H record: {h_rec}")
        start_address = int(m.group(2), 16)

        # --- Verify and load each T record ---
        t_pattern = re.compile(
            r"T\^([0-9A-Fa-f]{6})\^([0-9A-Fa-f]{2})\^([0-9A-Fa-f]+)"
            r":G:(\d+):(\d+):(\d+)$"
        )
        for t_rec in records["T"]:
            tm = t_pattern.match(t_rec)
            if not tm:
                raise ValueError(f"Malformed T record: {t_rec}")
            addr = int(tm.group(1), 16)
            byte_count = int(tm.group(2), 16)
            hex_data = tm.group(3)
            expected_s = int(tm.group(4))
            expected_l = int(tm.group(5))
            expected_r = int(tm.group(6))

            data_bytes = bytes.fromhex(hex_data)
            if len(data_bytes) != byte_count:
                raise ValueError(
                    f"T record byte count mismatch: declared {byte_count}, "
                    f"got {len(data_bytes)} at {addr:06X}"
                )

            s, l, r = gate231_compute_checksums(data_bytes)
            if (s, l, r) != (expected_s, expected_l, expected_r):
                raise ValueError(
                    f"231-gate checksum mismatch at {addr:06X}: "
                    f"expected G:{expected_s}:{expected_l}:{expected_r}, "
                    f"computed G:{s}:{l}:{r} — object code may be tampered"
                )

            # Load verified bytes into memory
            for i in range(0, len(hex_data), 2):
                self.memory.write_byte(addr + i // 2, int(hex_data[i:i+2], 16))

        # --- Parse E record (entry point) ---
        e_rec = records["E"]
        m = re.match(r"E\^([0-9A-Fa-f]{6})$", e_rec)
        if not m:
            raise ValueError(f"Malformed E record: {e_rec}")
        entry = int(m.group(1), 16)

        # Use E record entry point as initial PC (not H record start address)
        self.regs["PC"] = entry
        self.pc = entry
        return start_address

    def _read_word(self, addr):
        """Read 3 bytes (24-bit word) from addr."""
        return (self.memory.read_byte(addr) << 16) | (self.memory.read_byte(addr + 1) << 8) | self.memory.read_byte(addr + 2)

    def _write_word(self, addr, value):
        self.memory.write_byte(addr, (value >> 16) & 0xFF)
        self.memory.write_byte(addr + 1, (value >> 8) & 0xFF)
        self.memory.write_byte(addr + 2, value & 0xFF)

    def _fetch_instruction(self):
        """Fetch instruction at PC, return (byte1, opcode, format, ni, x, b, p, e, disp_or_addr, new_pc)."""
        pc = self.pc
        byte1 = self.memory.read_byte(pc)
        opcode6 = (byte1 >> 2) & 0x3F   # top 6 bits
        ni = byte1 & 0x03                # bottom 2 bits

        # Check for format 4: bit 8 of byte2 (e bit)
        byte2 = self.memory.read_byte(pc + 1)
        x = (byte2 >> 7) & 1
        b = (byte2 >> 6) & 1
        p = (byte2 >> 5) & 1
        e = (byte2 >> 4) & 1

        if e:
            # Format 4: 4 bytes total
            addr20 = ((byte2 & 0x0F) << 16) | (self.memory.read_byte(pc + 2) << 8) | self.memory.read_byte(pc + 3)
            return byte1, opcode6, 4, ni, x, b, p, e, addr20, pc + 4
        else:
            # Format 3: 3 bytes
            disp12 = ((byte2 & 0x0F) << 8) | self.memory.read_byte(pc + 2)
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
        # n=1,i=0 (indirect): value at (value at TA) -- memory indirect
        # n=0,i=1 (immediate): the value IS TA itself
        # n=0,i=0: (SIC/XE: SIC mode, treat as simple)
        if ni == 0b01:  # immediate: n=0, i=1
            return ta
        elif ni == 0b10:  # indirect: n=1, i=0
            addr = self._read_word(ta)
            return self._read_word(addr)
        else:  # simple: n=1, i=1 (or n=0,i=0 treated as simple)
            return self._read_word(ta)

    def _execute(self, byte1, opcode6, fmt, ni, x, b, p, e, disp, new_pc):
        """Execute an instruction. Returns (next_pc, trace_line, should_stop)."""
        # HALT instruction (opcode 0xFF)
        if byte1 == 0xFF:
            trace_line = f"  PC={self.pc:06X} HALT"
            return self.pc, trace_line, True

        # Map opcode to mnemonic for trace
        mnemonic = self._opcode_to_mnemonic(opcode6, fmt, byte1)
        trace_line = f"  PC={self.pc:06X} {mnemonic:<8} "

        # --- Simulator built-ins -------------------------------------------------
        # print_int at 0xFF00 (65280): print value in A register, return via L
        if self.pc == 65280:
            output = self.regs["A"]
            trace_line += f"PRINT_INT: A = {output}"
            self.regs["PC"] = self.regs["L"]
            self.pc = self.regs["L"]
            return self.regs["L"], trace_line, False

        # print at 0xFF03 (65283): print null-terminated string at address in A
        if self.pc == 65283:
            addr = self.regs["A"]
            chars = []
            while True:
                b = self.memory.read_byte(addr)
                if b == 0:
                    break
                chars.append(chr(b))
                addr += 1
            output = "".join(chars)
            trace_line += f"PRINT: {output!r}"
            self.regs["PC"] = self.regs["L"]
            self.pc = self.regs["L"]
            return self.regs["L"], trace_line, False

        # SVC handler at 0xFF06 (65286): system call dispatcher
        # SVC number read from memory location 0xFF07
        # A = arg1, X = arg2, TMP0 = arg3
        #   0: print_char (A = char)
        #   1: print_string (A = address of null-terminated string)
        #   2: read_char (returns char in A)
        #   3: open_file (A = address of filename, returns fd in A)
        #   4: read_file (A = fd, X = buffer addr, TMP0 = count, returns bytes read in A)
        #   5: write_file (A = fd, X = buffer addr, TMP0 = count, returns bytes written in A)
        #   6: close_file (A = fd)
        #   7: exit (A = exit code)
        if self.pc == 65286:
            svc_num = self.memory.read_byte(0xFF07)
            if svc_num == 0:  # print_char
                ch = self.regs["A"] & 0xFF
                trace_line += f"SVC putchar: {chr(ch) if 32 <= ch < 127 else f'\\\\x{ch:02x}'}"
                self.regs["PC"] = self.regs["L"]
                self.pc = self.regs["L"]
                return self.regs["L"], trace_line, False
            elif svc_num == 1:  # print_string
                addr = self.regs["A"]
                chars = []
                while True:
                    b = self.memory.read_byte(addr)
                    if b == 0:
                        break
                    chars.append(chr(b))
                    addr += 1
                output = "".join(chars)
                trace_line += f"SVC puts: {output!r}"
                self.regs["PC"] = self.regs["L"]
                self.pc = self.regs["L"]
                return self.regs["L"], trace_line, False
            elif svc_num == 2:  # read_char
                import sys as _sys
                ch_data = _sys.stdin.read(1)
                ch = ord(ch_data) if ch_data else -1
                self.regs["A"] = ch & 0xFF
                trace_line += f"SVC getchar: A = {ch}"
                self.regs["PC"] = self.regs["L"]
                self.pc = self.regs["L"]
                return self.regs["L"], trace_line, False
            elif svc_num == 3:  # open_file
                addr = self.regs["A"]
                fname = []
                while True:
                    b = self.memory.read_byte(addr)
                    if b == 0:
                        break
                    fname.append(chr(b))
                    addr += 1
                fname_str = "".join(fname)
                try:
                    f = open(fname_str, "r")
                    fd = id(f) & 0xFFFF
                    self._open_files[fd] = f
                    self.regs["A"] = fd
                    trace_line += f"SVC open: {fname_str!r} -> fd {fd}"
                except FileNotFoundError:
                    self.regs["A"] = -1 & 0xFFFF
                    trace_line += f"SVC open: {fname_str!r} -> not found"
                self.regs["PC"] = self.regs["L"]
                self.pc = self.regs["L"]
                return self.regs["L"], trace_line, False
            elif svc_num == 4:  # read_file
                fd = self.regs["A"]
                buf_addr = self.regs["X"]
                count = self.memory.read_byte(self.alloc_var("svc_count") if hasattr(self, 'alloc_var') else 0x1000)
                # Actually count is stored at TMP0 which is at a fixed location
                # Let's read count from memory location right after buf_addr
                count = self.memory.read_byte(buf_addr + 1)
                if fd not in self._open_files:
                    self.regs["A"] = -1 & 0xFFFF
                    trace_line += f"SVC read: fd {fd} not open"
                    self.regs["PC"] = self.regs["L"]
                    self.pc = self.regs["L"]
                    return self.regs["L"], trace_line, False
                f = self._open_files[fd]
                data = f.read(min(count, 256))
                for i, b in enumerate(data):
                    self.memory.write_byte(buf_addr + i, b)
                self.regs["A"] = len(data)
                trace_line += f"SVC read: fd {fd} -> {len(data)} bytes"
                self.regs["PC"] = self.regs["L"]
                self.pc = self.regs["L"]
                return self.regs["L"], trace_line, False
            elif svc_num == 5:  # write_file
                fd = self.regs["A"]
                buf_addr = self.regs["X"]
                count_addr = buf_addr + 1
                count = self.memory.read_byte(count_addr)
                data = bytes([self.memory.read_byte(buf_addr + i) for i in range(count)])
                if fd not in self._open_files:
                    self.regs["A"] = -1 & 0xFFFF
                    trace_line += f"SVC write: fd {fd} not open"
                    self.regs["PC"] = self.regs["L"]
                    self.pc = self.regs["L"]
                    return self.regs["L"], trace_line, False
                f = self._open_files[fd]
                f.write(data)
                self.regs["A"] = count
                trace_line += f"SVC write: fd {fd} -> {count} bytes"
                self.regs["PC"] = self.regs["L"]
                self.pc = self.regs["L"]
                return self.regs["L"], trace_line, False
            elif svc_num == 6:  # close_file
                fd = self.regs["A"]
                if fd in self._open_files:
                    self._open_files[fd].close()
                    del self._open_files[fd]
                    self.regs["A"] = 0
                    trace_line += f"SVC close: fd {fd}"
                else:
                    self.regs["A"] = -1 & 0xFFFF
                    trace_line += f"SVC close: fd {fd} not open"
                self.regs["PC"] = self.regs["L"]
                self.pc = self.regs["L"]
                return self.regs["L"], trace_line, False
            elif svc_num == 7:  # exit
                code = self.regs["A"]
                trace_line += f"SVC exit: code {code}"
                return self.pc, trace_line, True
            else:
                trace_line += f"SVC unknown: {svc_num}"
                return self.pc, trace_line, True

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
            # Halt if returning to address 0 (no return address set)
            if self.regs["L"] == 0:
                trace_line += " [HALT]"
                return self.regs["L"], trace_line, True
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
        if mnemonic == "STL":
            # Store L register to memory at TA (3 bytes, big-endian)
            l_val = self.regs["L"]
            self._write_word(ta, l_val)
            trace_line += f"L -> mem[{ta:06X}] = {l_val:06X}"
            self.pc = new_pc
            return new_pc, trace_line, False
        if mnemonic == "LDL":
            # Load L register from memory at TA (3 bytes, big-endian)
            l_val = self._read_target_value(ta, ni)
            self.regs["L"] = l_val & 0xFFFFFF
            trace_line += f"L <- mem[{ta:06X}] = {self.regs['L']:06X}"
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
        elif mnemonic == "AND":
            val = self._read_target_value(ta, ni)
            self.regs["A"] = (self.regs["A"] & val) & 0xFFFFFF
            trace_line += f"A <- A & mem[{ta:06X}] = {self.regs['A']:06X}"
        elif mnemonic == "OR":
            val = self._read_target_value(ta, ni)
            self.regs["A"] = (self.regs["A"] | val) & 0xFFFFFF
            trace_line += f"A <- A | mem[{ta:06X}] = {self.regs['A']:06X}"
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
        elif mnemonic == "JLE":
            if self.regs["SW"] in (0, 1):  # equal or less
                self.pc = ta
                trace_line += f"JLE taken -> {ta:06X}"
                return ta, trace_line, False
            trace_line += "JLE not taken"
        elif mnemonic == "JNE":
            if self.regs["SW"] != 0:  # not equal
                self.pc = ta
                trace_line += f"JNE taken -> {ta:06X}"
                return ta, trace_line, False
            trace_line += "JNE not taken"
        elif mnemonic == "JGE":
            if self.regs["SW"] in (0, 2):  # equal or greater
                self.pc = ta
                trace_line += f"JGE taken -> {ta:06X}"
                return ta, trace_line, False
            trace_line += "JGE not taken"
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

    # Simulate with 231-gate tamper verification
    print("\n--- Simulation Trace (231-gate verified load) ---")
    sim = Simulator()
    try:
        start = sim.verify_and_load_records(records)
        print(f"  231-gate verification PASSED — all T records intact, entry at {start:06X}")
    except ValueError as e:
        print(f"  231-gate verification FAILED: {e}")
        return 1
    trace = sim.run()

    for line in trace:
        print(line)

    print("\n--- Final Register State ---")
    for reg in ["A", "X", "L", "B", "S", "T", "F", "PC", "SW"]:
        print(f"  {reg} = {sim.regs[reg]:06X}")

    # Tamper-detection test: flip one byte in a T record and confirm rejection
    print("\n--- Tamper Detection Test ---")
    tampered = dict(records)
    tampered_t = []
    for t in records["T"]:
        # Flip the last hex digit of the data in the first T record only
        if tampered_t == []:
            parts = t.split(":G:")[0]
            # Split into T^addr^len^hexdata
            prefix, hexdata = parts.rsplit("^", 1)
            if len(hexdata) >= 2:
                # Flip last nibble
                last = int(hexdata[-1], 16) ^ 0x1
                hexdata = hexdata[:-1] + f"{last:X}"
            tampered_t.append(prefix + "^" + hexdata + ":G:" + t.split(":G:")[1])
        else:
            tampered_t.append(t)
    tampered["T"] = tampered_t

    sim2 = Simulator()
    try:
        sim2.verify_and_load_records(tampered)
        print("  Tampered T record was ACCEPTED — VERIFICATION BROKEN")
        return 1
    except ValueError as e:
        print(f"  Tampered T record REJECTED: {e}")
        print("  231-gate tamper detection: PASS")

    print("\n" + "=" * 70)
    print("VERIFICATION: JSUB sets L = return address; RSUB restores PC from L")
    print("              Indexed addressing: TA = address + (X)")
    print("              231-gate: object code is tamper-evident")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
