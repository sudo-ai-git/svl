#!/usr/bin/env python3
"""Multi-file SVL -> SIC/XE -> link -> execute pipeline test.

Compiles two SVL source files to object code, links them with the
231-gate-verified linker, loads the linked image, and checks output.

  test_utils.svl   defines add(a,b) and mul(a,b)
  test_main2.svl   main() calls add(3,4) and mul(3,4), prints "7 12"
"""

import sys
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Works whether this file sits at the repo root or in tests/
ROOT = HERE if (HERE / "svl_to_sic.py").exists() else HERE.parent
sys.path.insert(0, str(ROOT))

from sic_xe_assembler_sim import Simulator


def compile_to_obj(svl_path: Path) -> Path:
    """Compile an SVL file to a .obj via svl_to_sic.py --emit-obj."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "svl_to_sic.py"), str(svl_path), "--emit-obj"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if r.returncode != 0:
        raise RuntimeError(f"compile failed for {svl_path}:\n{r.stdout}\n{r.stderr}")
    return svl_path.with_suffix(".obj")


def link(objs, out_path: Path) -> Path:
    r = subprocess.run(
        [sys.executable, str(ROOT / "sic_xe_linker.py"), *[str(o) for o in objs],
         "-o", str(out_path)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if r.returncode != 0:
        raise RuntimeError(f"link failed:\n{r.stdout}\n{r.stderr}")
    return out_path


def run_object(obj_path: Path):
    """Load and run an object file; return (trace_lines, regs)."""
    lines = obj_path.read_text().strip().splitlines()
    records = {
        "H": [l for l in lines if l.startswith("H^")][0],
        "T": [l for l in lines if l.startswith("T^")],
        "E": [l for l in lines if l.startswith("E^")][0],
    }
    sim = Simulator()
    sim.verify_and_load_records(records)
    return sim.run(), sim.regs


def main():
    utils_obj = compile_to_obj(HERE / "test_utils.svl")
    main_obj = compile_to_obj(HERE / "test_main2.svl")
    linked = link([utils_obj, main_obj], HERE / "linked_test.obj")

    trace, regs = run_object(linked)

    printed = "".join(
        line.split("PRINT:", 1)[1].strip().strip("'").replace("\\n", "\n").replace("\\t", "\t")
        for line in trace if "PRINT:" in line
    )
    # print_int lines are not captured by the PRINT: filter; reconstruct from trace
    ints = []
    for line in trace:
        if "PRINT_INT:" in line:
            ints.append(line.split("PRINT_INT:", 1)[1].strip())

    print("Linked object:", linked)
    print("print_int values:", ints)
    print("PRINT strings:", [l.split('PRINT:', 1)[1] for l in trace if 'PRINT:' in l])

    # Expected: add(3,4)=7, mul(3,4)=12 -> print_int 7, " ", print_int 12, "\n"
    ok = ints == ["A = 7", "A = 12"]
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
