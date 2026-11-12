#!/usr/bin/env python3
"""Spike 017: demote the constant-true BPSW layer to informational (L1)."""
import dataclasses
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402
from svl.theorem_layer import TheoremLayer                     # noqa: E402

_orig = TheoremLayer.verify_theorem


def patched(self, source):
    r = _orig(self, source)
    passed = (r.syntax_layer_verified and r.type_layer_verified
              and r.smt_verified)          # BPSW deliberately excluded
    r = dataclasses.replace(r, passed=passed)
    r.bpsw_status = "informational"
    return r


def main():
    try:
        layer = TheoremLayer()
        same = True
        checked = 0
        for i in range(60):
            src = (f"module m {{ func main() type int {{ let x = {i}"
                   f" return x + 1 }} }}")
            a = _orig(layer, src)
            b = patched(layer, src)
            checked += 1
            if a.passed != b.passed:
                same = False
        # and a program that fails syntax must still fail
        bad = _orig(layer, "module m { func main() type int { return \"hi\" } }")
        bad2 = patched(layer, "module m { func main() type int { return \"hi\" } }")
        honest = (bad2.passed == bad.passed)
        ok = same and honest
        return verdict("017-demote-bpsw", ok,
                       f"{checked}/60 verdicts unchanged by dropping BPSW; "
                       f"bpsw_status={getattr(patched(layer, 'module m { func main() type int { return 1 } }'), 'bpsw_status', None)}")
    except Exception as exc:
        return verdict("017-demote-bpsw", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
