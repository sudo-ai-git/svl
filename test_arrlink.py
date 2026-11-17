#!/usr/bin/env python3
"""Cross-file array-argument test: compile two SVL files, link, run.

test_arr_utils.svl defines arrsum(a:[int], n:int); test_arr_main.svl builds an
array and calls it. Exercises array parameters across an object-file link
(the argument slots at 0xF000 are a shared convention).
"""

import sys
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "svl_to_sic.py").exists() else HERE.parent
sys.path.insert(0, str(ROOT))

from sic_xe_assembler_sim import Simulator


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))


def main():
    for name in ("test_arr_utils", "test_arr_main"):
        r = run([sys.executable, "svl_to_sic.py", str(HERE / f"{name}.svl"), "--emit-obj"])
        if r.returncode != 0:
            print("compile failed:", name, r.stdout, r.stderr)
            return 1

    linked = HERE / "arr_linked.obj"
    r = run([sys.executable, "sic_xe_linker.py",
             str(HERE / "test_arr_utils.obj"), str(HERE / "test_arr_main.obj"),
             "-o", str(linked)])
    if r.returncode != 0:
        print("link failed:", r.stdout, r.stderr)
        return 1

    lines = linked.read_text().strip().splitlines()
    records = {
        "H": [l for l in lines if l.startswith("H^")][0],
        "T": [l for l in lines if l.startswith("T^")],
        "E": [l for l in lines if l.startswith("E^")][0],
    }
    sim = Simulator()
    sim.verify_and_load_records(records)
    ints = [l.split("A = ")[1].strip() for l in sim.run() if "PRINT_INT" in l]
    print("print_int values:", ints)
    ok = ints == ["26"]
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
