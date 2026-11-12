#!/usr/bin/env python3
"""Spike 019: put the SMT prover on an opt-in compile path (F4/L1)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, "/home/sudosudo/.openclaw/workspace")

from harness import verdict                                    # noqa: E402
import svl.compiler_wasm as cw                                  # noqa: E402
from svl.verify_gate import SVLVerificationError                # noqa: E402

_orig = cw.compile_file_to_wasm


def patched(source, strict=True, deterministic=True, attest=False, prove=False):
    wat = _orig(source, strict=strict, deterministic=deterministic, attest=attest)
    if prove:
        from svl.smt_theorem import verify_with_smt
        r = verify_with_smt(source)
        if r.status == "counterexample":
            raise SVLVerificationError(
                f"SMT counterexample: {r.error_message or 'assertion refuted'}")
    return wat


def main():
    try:
        cw.compile_file_to_wasm = patched
        false_assert = ("module m { func f(a: int) type int { assert a > 0 return 0 } }")
        true_assert = ("module m { func f(a: int) type int { assert a + 1 > a return 0 } }")
        refused = False
        try:
            patched(false_assert, prove=True)
        except SVLVerificationError:
            refused = True
        proven = False
        try:
            patched(true_assert, prove=True)
            proven = True
        except SVLVerificationError:
            proven = False
        ok = refused and proven
        return verdict("019-smt-opt-in-compile", ok,
                       f"false assert refused={refused}; true assert accepted={proven}")
    except Exception as exc:
        return verdict("019-smt-opt-in-compile", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
