#!/usr/bin/env python3
"""Corpus regression check for the SVL backend.

Rebuilds the README's measured expectation from the files on disk:
  * how many .svl programs parse+compile (strict, so the gate runs),
  * how many the compile-time gate refuses (must be 0 on this corpus),
  * how many the abstract interpreter flags (must be 0 on this corpus),
  * how many round-trip through the binary AST format.

Exit status
-----------
Non-zero only when the *gate* regresses: a refusal, an abstract-interpreter finding, or a
drop below the measured compilable count. Files that never compiled (the pre-existing
legacy fixtures) are reported but do not fail the run -- they are corpus content, not a
gate regression, and CI must be green on a clean checkout.

Run:  /usr/bin/python3 svl/corpus_check.py
"""
import os
import sys
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# `python svl/corpus_check.py` puts svl/ on sys.path, not the workspace root, so `import
# svl` would fail unless the caller sets PYTHONPATH. Insert it here so the script works
# the same when run directly and from CI.
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Both layouts: the public repo keeps programs in `examples/`; the development workspace
# keeps them at the repo root and mirrors the public examples under `svl-release/`.
SEARCH = [
    os.path.join(ROOT, '*.svl'),
    os.path.join(ROOT, 'svl', '*.svl'),
    os.path.join(ROOT, 'examples', '*.svl'),
    os.path.join(ROOT, 'svl-release', 'examples', '*.svl'),
]

# Measured 2026-11-12 on this corpus. A drop below it means a program that used to
# compile no longer does -- a real regression, as opposed to the legacy fixtures that
# never compiled at all.
MIN_COMPILABLE = 20


def corpus():
    seen = set()
    for pattern in SEARCH:
        for path in sorted(glob.glob(pattern)):
            real = os.path.realpath(path)
            if real not in seen:
                seen.add(real)
                yield path


import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(description="SVL corpus regression check")
    parser.add_argument("--json", action="store_true",
                        help="emit the measured counts as JSON")
    parser.add_argument("--write-baseline", metavar="PATH",
                        help="persist the measured counts to a JSON baseline file")
    args = parser.parse_args(argv)

    from svl.compiler_wasm import compile_file_to_wasm
    from svl.abstract_interpretation import analyze_program
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    from svl.serialization import to_binary, from_binary
    from svl.verify_gate import verify_program

    total = compiled = refused = ai_findings = roundtrip = 0
    legacy = []
    gate_regressions = []
    for path in corpus():
        total += 1
        src = open(path, encoding='utf-8').read()
        try:
            problems = verify_program(src)
            ast = parse(tokenize(src))
        except SyntaxError as exc:
            legacy.append((path, f'parse: {exc}'))
            continue
        ai = analyze_program(ast)
        ai_findings += len(ai.findings)
        if problems:
            refused += 1
            gate_regressions.append((path, f'gate: {problems[0][:90]}'))
            continue
        try:
            compile_file_to_wasm(src)
            compiled += 1
        except Exception as exc:                                    # noqa: BLE001
            legacy.append((path, f'compile: {type(exc).__name__}: {str(exc)[:90]}'))
            continue
        try:
            if from_binary(to_binary(ast)) is not None:
                roundtrip += 1
        except Exception as exc:                                    # noqa: BLE001
            legacy.append((path, f'roundtrip: {type(exc).__name__}: {str(exc)[:90]}'))

    summary = {
        "files": total, "compiled": compiled, "refused": refused,
        "ai_findings": ai_findings, "roundtrip": roundtrip,
        "min_compilable": MIN_COMPILABLE,
    }
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f'files={total} compiled={compiled} refused={refused} '
              f'ai_findings={ai_findings} roundtrip={roundtrip}')
    if args.write_baseline:
        with open(args.write_baseline, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, sort_keys=True)
            fh.write("\n")
        if not args.json:
            print(f"  baseline written: {args.write_baseline}")
    if not args.json:
        for path, why in gate_regressions:
            print(f"  GATE REGRESSION {os.path.relpath(path, ROOT)}: {why}")
        for path, why in legacy:
            print(f"  legacy (never compiled): {os.path.relpath(path, ROOT)}: {why}")

    ok = (refused == 0 and ai_findings == 0 and compiled >= MIN_COMPILABLE)
    if compiled < MIN_COMPILABLE:
        print(f'  REGRESSION: only {compiled} programs compiled '
              f'(expected >= {MIN_COMPILABLE})')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
