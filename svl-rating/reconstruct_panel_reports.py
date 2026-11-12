#!/usr/bin/env python3
"""Reconstruct the 5 expert reports from all_improvements.json.

The first panel run overwrote per-child report files (delegate_task results carry no
`name`), so only the last child survived as `?.txt`.  The proposals themselves are all
present in `all_improvements.json`; this writes one readable file per expert, grouped by
the task-index ranges the panel was spawned in (0-5 semantics, 6-11 types, 12-17 runtime,
18-23 verification, 24-29 tooling).

Run:  python svl-rating/reconstruct_panel_reports.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "panel_raw")
LENSES = {
    "0-5": "language semantics & compiler correctness",
    "6-11": "type system & soundness",
    "12-17": "runtime, codegen & memory",
    "18-23": "verification & assurance",
    "24-29": "tooling, DX & ecosystem",
}


def main():
    imps = json.load(open(os.path.join(RAW, "all_improvements.json")))
    for rng, lens in LENSES.items():
        lo, hi = map(int, rng.split("-"))
        group = [imp for i, imp in enumerate(imps) if lo <= i <= hi]
        if not group:
            continue
        path = os.path.join(RAW, f"expert_{lo:02d}_{hi:02d}.md")
        with open(path, "w") as fh:
            fh.write(f"# Expert report — {lens}\n\n")
            for imp in group:
                fh.write(f"## {imp.get('id')}  (addresses {imp.get('addresses')}, "
                         f"effort {imp.get('effort')}, risk {imp.get('risk')})\n\n")
                fh.write(f"**Problem.** {imp.get('problem')}\n\n")
                fh.write(f"**Proposal.** {imp.get('proposal')}\n\n")
                fh.write(f"**Expected.** {imp.get('expected_effect')}\n\n")
                fh.write(f"**Spike.** {imp.get('spike_question')}\n\n")
        print(f"wrote {path} ({len(group)} proposals)")
    # remove the collapsed file
    junk = os.path.join(RAW, "?.txt")
    if os.path.exists(junk):
        os.unlink(junk)
        print(f"removed {junk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
