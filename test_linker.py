#!/usr/bin/env python3
"""Test the SIC/XE linker with two object files."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sic_xe_assembler_sim import Assembler, parse_source
from sic_xe_linker import parse_object_file, Linker, emit_linked_object


def assemble_source(source_text, name):
    """Assemble source text and return (object_file_path, sym_file_path)."""
    src_lines = parse_source(source_text)
    asm = Assembler(src_lines)
    success, records = asm.assemble()
    if not success:
        print(f"Assembly failed for {name}: {asm.errors}")
        return None, None

    base = f"/tmp/test_{name}"
    obj_path = f"{base}.obj"
    sym_path = f"{base}.sym"

    # Write object file
    lines = [records["H"]]
    lines.extend(records["T"])
    lines.append(records["E"])
    Path(obj_path).write_text("\n".join(lines) + "\n")

    # Write symbol file
    asm.write_symbol_file(sym_path)

    return obj_path, sym_path


def main():
    # Object file 1: defines FUNC_A, calls FUNC_B
    obj1_src = """        START  1000
MAIN     JSUB   FUNC_B
         LDA    #1
         STA    RESULT
         HALT
RESULT   RESW   1
         END    MAIN
"""
    # Object file 2: defines FUNC_B
    obj2_src = """        START  2000
FUNC_B   LDA    #42
         STA    RESULT+1
         RSUB
         END    FUNC_B
"""

    obj1_path, sym1_path = assemble_source(obj1_src, "obj1")
    obj2_path, sym2_path = assemble_source(obj2_src, "obj2")

    if not obj1_path or not obj2_path:
        return 1

    # Parse object files
    obj1 = parse_object_file(Path(obj1_path))
    obj2 = parse_object_file(Path(obj2_path))

    print(f"obj1: {obj1.name}, defined={list(obj1.defined_symbols.keys())}, "
          f"undefined={list(obj1.undefined_symbols.keys())}")
    print(f"obj2: {obj2.name}, defined={list(obj2.defined_symbols.keys())}, "
          f"undefined={list(obj2.undefined_symbols.keys())}")

    # Link
    linker = Linker()
    linker.add_object(obj1)
    linker.add_object(obj2)

    try:
        result = linker.link()
    except ValueError as e:
        print(f"Link error: {e}")
        return 1

    print(f"\nLinked: total_length={result['total_length']:06X}, "
          f"entry={result['entry_addr']:06X}")
    print(f"Global symbols: {result['global_symbols']}")

    # Emit linked object
    output_text = emit_linked_object(result, name="LINKED",
                                     start=result["entry_addr"])
    out_path = "/tmp/linked.obj"
    Path(out_path).write_text(output_text + "\n")
    print(f"\nWritten linked object to {out_path}")
    print(output_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
