#!/usr/bin/env python3
"""Build a self-attested SVL artifact and verify it independently.

    python3 examples/attest.py examples/sieve.svl
    python3 examples/attest.py examples/sieve.svl --out /tmp/sieve.wasm
    python3 examples/attest.py --verify /tmp/sieve.wasm

Why this exists: SVL's compilation is a pure function of the AST (the same source always
produces the same bytes), which is the design's most distinctive property. This turns that
property into a *checkable* attestation instead of a drift detector.

The attestation binds three things into a `svl.attest` custom section:
  * `content_sha256` — SHA-256 of the artifact with all custom sections stripped
  * `gate231`        — the three 231-gate checksums of the serialised AST
  * `ast_sha256`     — SHA-256 of the serialised AST

`--verify` re-derives `content_sha256` from the artifact it is handed and compares. Because
the hash covers every non-custom section, any change to the code fails verification.

This is NOT the `pcc_wasm` proof, which embeds a self-declared boolean produced by the same
process that produced the artifact and therefore checks nothing.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from svl.attest import compile_attested, verify_attestation, locate_sync  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--out", default=None, help="write the attested .wasm here")
    ap.add_argument("--verify", default=None, metavar="WASM",
                    help="verify an existing attested artifact instead of building one")
    ap.add_argument("--locate", default=None, metavar="STREAM",
                    help="find this artifact's sync block inside another file "
                         "(self-framing resync; prints candidate offsets)")
    args = ap.parse_args(argv[1:])

    if args.locate:
        if not args.path:
            print("--locate needs the artifact path as well")
            return 2
        source = open(args.path).read()
        _wat, binary, payload = compile_attested(source)
        stream = open(args.locate, "rb").read()
        starts = locate_sync(stream, payload["sync"])
        print(f"artifact : {args.path}")
        print(f"stream   : {args.locate} ({len(stream)} bytes)")
        print(f"sync     : block={payload['sync']['block']} "
              f"checksums={payload['sync']['checksums']} meta={payload['sync']['meta']}")
        print(f"starts   : {starts}")
        print("note     : the PRODUCT channel is degenerate at this block size, so treat "
              "this as a candidate list (see svl.attest.locate_sync).")
        return 0

    if args.verify:
        binary = open(args.verify, "rb").read()
        ok, details = verify_attestation(binary)
        payload = details.get("payload") or {}
        print(f"artifact      : {args.verify} ({len(binary)} bytes)")
        print(f"claimed hash  : {str(details.get('claimed'))[:32]}...")
        print(f"recomputed    : {str(details.get('actual'))[:32]}...")
        print(f"ast_sha256    : {str(payload.get('ast_sha256'))[:32]}...")
        print(f"gate231       : {payload.get('gate231')}")
        print(f"ATTESTATION   : {'VALID' if ok else 'INVALID — ' + str(details.get('error') or 'hash mismatch')}")
        return 0 if ok else 1

    if not args.path:
        print(__doc__)
        return 2

    source = open(args.path).read()
    # The compile path runs the verification gate; a violation raises here.  compile_attested
    # is the artifact-producing entry point: it binds the artifact to its canonical AST
    # fingerprint via the svl.attest custom section.
    attested_wat, binary, payload = compile_attested(source)

    out = args.out or os.path.splitext(args.path)[0] + ".wasm"
    with open(out, "wb") as fh:
        fh.write(binary)

    print(f"source        : {args.path}")
    print(f"artifact      : {out} ({len(binary)} bytes)")
    print(f"content_sha256: {payload['content_sha256']}")
    print(f"ast_sha256    : {payload['ast_sha256']}")
    print(f"gate231       : {payload['gate231']}")
    print(f"wat sha256    : {hashlib.sha256(attested_wat.encode()).hexdigest()}")
    print(f"artifact sha  : {hashlib.sha256(binary).hexdigest()}")

    ok, details = verify_attestation(binary)
    print(f"self-check    : {'VALID' if ok else 'INVALID'}")
    print()
    print("verify it independently with:")
    print(f"  python3 examples/attest.py --verify {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
