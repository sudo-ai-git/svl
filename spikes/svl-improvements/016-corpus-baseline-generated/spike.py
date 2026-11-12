#!/usr/bin/env python3
"""Spike 016: generate the README corpus baseline instead of hand-writing it (L4)."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402

REPO = "/home/sudosudo/svl-release"     # the mirror whose README carries the claim
README = "/home/sudosudo/svl-release/README.md"


def main():
    try:
        p = subprocess.run([sys.executable, os.path.join(REPO, "svl", "corpus_check.py")],
                           capture_output=True, text=True, cwd=REPO, timeout=300)
        m = re.search(r"files=(\d+) compiled=(\d+) refused=(\d+)", p.stdout)
        if not m:
            return verdict("016-corpus-baseline-generated", False,
                           f"no summary line: {p.stdout[:200]}")
        files, compiled, refused = map(int, m.groups())
        readme = open(README).read()
        claim = re.search(r"(\d+)\s+files?,?\s+\*{0,2}(\d+)\s+compilable", readme)
        claim_n = (int(claim.group(1)), int(claim.group(2))) if claim else None
        generated = f"{files} files, {compiled} compilable"
        ok = (claim_n != (files, compiled))
        return verdict("016-corpus-baseline-generated", ok,
                       f"measured={generated}; README claims {claim_n}; "
                       f"generated line differs from the stale claim = {ok}")
    except Exception as exc:
        return verdict("016-corpus-baseline-generated", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
