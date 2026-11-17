#!/usr/bin/env python3
"""
SIC/XE Linking Loader

Combines multiple SIC/XE object files (H/T/E records) into a single executable
with relocation. Resolves external references (EXTERN/ENTRY) across object files.

Usage:
  python3 sic_xe_linker.py obj1.obj obj2.obj ... -o linked.obj

Object file format: H/T/E records produced by sic_xe_assembler_sim.py
Output: single H/T/E object file with all code relocated and external refs resolved
"""

import sys
import re
import json
from pathlib import Path


# ═════════════════════════════════════════════════════════════════════════════
# OBJECT RECORD PARSER
# ═════════════════════════════════════════════════════════════════════════════

class ObjectFile:
    """A single SIC/XE object file (H/T/E records)."""

    def __init__(self, name: str, start: int, length: int, entry: int,
                 t_records: list):
        self.name = name
        self.start = start          # load address (before relocation)
        self.length = length        # program length in bytes
        self.entry = entry          # entry point address
        self.t_records = t_records  # list of (addr, byte_count, hex_data,
                                    #               sum, lin, rol)
        self.defined_symbols = {}   # symbol -> address (relative to start)
        self.undefined_symbols = {} # symbol -> [(addr, offset_within_instr), ...]

    def add_defined(self, symbol: str, addr: int):
        self.defined_symbols[symbol] = addr

    def add_undefined(self, symbol: str, addr: int, offset: int = 0):
        self.undefined_symbols.setdefault(symbol, []).append((addr, offset))


def parse_object_file(path: Path) -> ObjectFile:
    """Parse H/T/E object file into ObjectFile structure."""
    text = path.read_text()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    h_record = None
    t_records = []
    e_record = None

    for line in lines:
        if line.startswith("H^"):
            h_record = line
        elif line.startswith("T^"):
            t_records.append(line)
        elif line.startswith("E^"):
            e_record = line

    if not h_record:
        raise ValueError(f"Missing H record in {path}")
    if not e_record:
        raise ValueError(f"Missing E record in {path}")

    # Parse H: H^name^start^length
    h_parts = h_record.split("^")
    name = h_parts[1]
    start = int(h_parts[2], 16)
    length = int(h_parts[3], 16)

    # Parse E: E^entry
    e_parts = e_record.split("^")
    entry = int(e_parts[1], 16)

    # Parse T records
    parsed_t = []
    t_pattern = re.compile(
        r"T\^([0-9A-Fa-f]{6})\^([0-9A-Fa-f]{2})\^([0-9A-Fa-f]+)"
        r":G:(\d+):(\d+):(\d+)$"
    )
    for t in t_records:
        tm = t_pattern.match(t)
        if not tm:
            raise ValueError(f"Malformed T record: {t}")
        addr = int(tm.group(1), 16)
        byte_count = int(tm.group(2), 16)
        hex_data = tm.group(3)
        g_sum = int(tm.group(4), 10)
        g_lin = int(tm.group(5), 10)
        g_rol = int(tm.group(6), 10)
        parsed_t.append((addr, byte_count, hex_data, g_sum, g_lin, g_rol))

    obj = ObjectFile(name, start, length, entry, parsed_t)

    # Load symbol sidecar file (.sym) if present
    sym_path = path.with_suffix(".sym")
    if sym_path.exists():
        sym_text = sym_path.read_text()
        for line in sym_text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if parts[0] == "D" and len(parts) == 3:
                sym_name = parts[1]
                sym_addr = int(parts[2], 16)
                obj.add_defined(sym_name, sym_addr)
            elif parts[0] == "U" and len(parts) == 3:
                sym_name = parts[1]
                ref_addr = int(parts[2], 16)
                obj.add_undefined(sym_name, ref_addr)

    return obj


# ═════════════════════════════════════════════════════════════════════════════
# LINKER
# ═════════════════════════════════════════════════════════════════════════════

class Linker:
    """Relocating linking loader for SIC/XE object files."""

    def __init__(self):
        self.objects = []           # list of ObjectFile
        self.global_symbols = {}    # symbol -> absolute address
        self.next_load_addr = 0     # next free load address

    def add_object(self, obj: ObjectFile):
        self.objects.append(obj)

    def resolve_symbols(self):
        """Pass 1: assign absolute addresses and build global symbol table."""
        for obj in self.objects:
            obj.load_addr = self.next_load_addr
            # All labels in this object are defined at load_addr + (rel_addr - start)
            for sym, rel_addr in obj.defined_symbols.items():
                abs_addr = self.next_load_addr + (rel_addr - obj.start)
                if sym in self.global_symbols:
                    # Keep first definition (runtime subroutines are identical
                    # across object files); skip duplicates.
                    continue
                self.global_symbols[sym] = abs_addr
            self.next_load_addr += obj.length

    def resolve_references(self):
        """Pass 2: resolve undefined symbols using global symbol table."""
        for obj in self.objects:
            for sym, refs in obj.undefined_symbols.items():
                if sym not in self.global_symbols:
                    raise ValueError(
                        f"Undefined symbol '{sym}' referenced in {obj.name}"
                    )
                abs_addr = self.global_symbols[sym]
                for ref_addr, offset in refs:
                    # ref_addr is in the object's own address space; yield the
                    # linked-image address of the instruction plus the resolved target
                    patch_linked = obj.load_addr + (ref_addr - obj.start)
                    yield patch_linked, abs_addr, offset

    def link(self) -> dict:
        """Produce linked object file records.

        Pass 1: assign load addresses and build global symbol table.
        Pass 2: relocate T record addresses and patch undefined symbol
                references in instruction address fields.
        """
        self.resolve_symbols()

        # Collect all relocated T records, patching undefined symbol refs
        linked_t = []
        for obj in self.objects:
            load_offset = obj.load_addr - obj.start
            for addr, byte_count, hex_data, g_sum, g_lin, g_rol in obj.t_records:
                abs_addr = obj.load_addr + (addr - obj.start)

                # Convert hex to bytearray for patching
                bytes_list = list(bytes.fromhex(hex_data))

                # Patch undefined symbol references in this T record's range
                for sym, refs in obj.undefined_symbols.items():
                    abs_sym_addr = self.global_symbols[sym]
                    for ref_addr, offset in refs:
                        # ref_addr is in the object's own address space
                        if addr <= ref_addr < addr + byte_count:
                            rel_offset = ref_addr - addr
                            if rel_offset + 3 <= len(bytes_list):
                                # Patch the address/displacement field.
                                # Preserve existing xbpe bits (high nibble of byte2),
                                # only update the address/displacement field.
                                full_addr = (abs_sym_addr + offset) & 0xFFFFFF
                                # Linked-image address of this instruction
                                patch_linked = obj.load_addr + (ref_addr - obj.start)
                                byte2_orig = bytes_list[rel_offset + 1]
                                e_bit = (byte2_orig >> 4) & 1
                                if e_bit:
                                    # Format 4: full 20-bit absolute address spans bytes 1-3
                                    bytes_list[rel_offset + 1] = \
                                        (byte2_orig & 0xF0) | ((full_addr >> 16) & 0x0F)
                                    bytes_list[rel_offset + 2] = (full_addr >> 8) & 0xFF
                                    bytes_list[rel_offset + 3] = full_addr & 0xFF
                                else:
                                    # Format 3: 12-bit PC-relative displacement.
                                    # Force p=1, b=0 so the resolved target is
                                    # reached relative to PC (the placeholder was
                                    # assembled base-relative because target 0 was
                                    # out of PC range).
                                    disp = (abs_sym_addr - patch_linked - 3) & 0xFFF
                                    x_bit = (byte2_orig >> 7) & 1
                                    new_xbpe = (x_bit << 3) | 0b0010  # x, b=0, p=1, e=0
                                    bytes_list[rel_offset + 1] = \
                                        (new_xbpe << 4) | (disp >> 8)
                                    bytes_list[rel_offset + 2] = disp & 0xFF

                # Recompute hex from patched bytes
                new_hex = bytes(bytes_list).hex()

                # Recompute 231-gate checksum for patched record
                from svl.gate231 import compute_checksums as gate231_compute
                new_s, new_l, new_r = gate231_compute(bytes.fromhex(new_hex))

                linked_t.append((abs_addr, byte_count, new_hex,
                                 new_s, new_l, new_r))

        # Total program length
        total_length = self.next_load_addr

        # Entry point: last object's entry, relocated (main program is linked last)
        entry_addr = self.objects[-1].load_addr + (
            self.objects[-1].entry - self.objects[-1].start
        )

        return {
            "linked_t": linked_t,
            "total_length": total_length,
            "entry_addr": entry_addr,
            "global_symbols": self.global_symbols,
        }


def emit_linked_object(result: dict, name: str = "LINKED",
                       start: int = 0) -> str:
    """Emit linked object as H/T/E records."""
    lines = []

    # H record (name field is 6 chars in the SIC/XE object format)
    lines.append(f"H^{name[:6]:<6}^{start:06X}^{result['total_length']:06X}")

    # T records - merge contiguous bytes into records of max 60 bytes
    t_records = result["linked_t"]
    if t_records:
        # Sort by address
        t_records.sort(key=lambda x: x[0])

        current_start = t_records[0][0]
        current_bytes = []
        current_end = current_start

        for addr, byte_count, hex_data, g_sum, g_lin, g_rol in t_records:
            if addr != current_end or len(current_bytes) + byte_count > 60:
                if current_bytes:
                    hex_str = "".join(current_bytes)
                    # Recompute 231-gate checksum for merged record
                    from svl.gate231 import compute_checksums as gate231_compute
                    s, l, r = gate231_compute(bytes.fromhex(hex_str))
                    lines.append(
                        f"T^{current_start:06X}^{len(hex_str)//2:02X}^{hex_str}"
                        f":G:{s}:{l}:{r}"
                    )
                current_start = addr
                current_bytes = [hex_data]
                current_end = addr + byte_count
            else:
                current_bytes.append(hex_data)
                current_end = addr + byte_count

        if current_bytes:
            hex_str = "".join(current_bytes)
            from svl.gate231 import compute_checksums as gate231_compute
            s, l, r = gate231_compute(bytes.fromhex(hex_str))
            lines.append(
                f"T^{current_start:06X}^{len(hex_str)//2:02X}^{hex_str}"
                f":G:{s}:{l}:{r}"
            )

    # E record
    lines.append(f"E^{result['entry_addr']:06X}")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 sic_xe_linker.py <obj1.obj> [obj2.obj ...] -o <out.obj>")
        return 1

    # Parse args
    input_files = []
    output_file = "linked.obj"
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "-o" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        else:
            input_files.append(sys.argv[i])
            i += 1

    if not input_files:
        print("Error: no input files")
        return 1

    # Parse all object files
    objects = []
    for f in input_files:
        path = Path(f)
        if not path.exists():
            print(f"Error: file not found: {f}")
            return 1
        obj = parse_object_file(path)
        objects.append(obj)
        print(f"Loaded {f}: {obj.name}, start={obj.start:06X}, "
              f"length={obj.length:06X}, entry={obj.entry:06X}")

    # Link
    linker = Linker()
    for obj in objects:
        linker.add_object(obj)

    try:
        result = linker.link()
    except ValueError as e:
        print(f"Link error: {e}")
        return 1

    print(f"\nLinked {len(objects)} object(s):")
    print(f"  Total length: {result['total_length']:06X} bytes")
    print(f"  Entry point: {result['entry_addr']:06X}")
    print(f"  Global symbols:")
    for sym, addr in sorted(result["global_symbols"].items()):
        print(f"    {sym:<16} = {addr:06X}")

    # Emit
    output_text = emit_linked_object(result, name=Path(output_file).stem,
                                     start=result["entry_addr"])
    Path(output_file).write_text(output_text + "\n")
    print(f"\nWritten linked object to {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
