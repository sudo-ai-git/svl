#!/usr/bin/env python3
"""Corpus regression check for the SVL backend.

Rebuilds the README's measured expectation from the files on disk:
  * how many .svl programs parse+compile (strict, so the gate runs),
  * how many the abstract interpreter refuses (must be 0 on this corpus),
  * how many round-trip through the binary AST format.

Run:  /usr/bin/python3 svl/corpus_check.py
"""
import os
import sys
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH = [
    os.path.join(ROOT, '*.svl'),
    os.path.join(ROOT, 'svl', '*.svl'),
    os.path.join(ROOT, 'svl-release', 'examples', '*.svl'),
]


def corpus():
    seen = set()
    for pattern in SEARCH:
        for path in sorted(glob.glob(pattern)):
            real = os.path.realpath(path)
            if real not in seen:
                seen.add(real)
                yield path


def main():
    from svl.compiler_wasm import compile_file_to_wasm
    from svl.abstract_interpretation import analyze_program
    from svl.lexer import tokenize
    from svl.parser_rd import parse
    from svl.serialization import to_binary, from_binary
    from svl.verify_gate import verify_program

    total = compiled = refused = ai_findings = roundtrip = 0
    failures = []
    for path in corpus():
        total += 1
        src = open(path, encoding='utf-8').read()
        try:
            problems = verify_program(src)
            ast = parse(tokenize(src))
        except SyntaxError as exc:
            failures.append((path, f'parse: {exc}'))
            continue
        ai = analyze_program(ast)
        ai_findings += len(ai.findings)
        if problems:
            refused += 1
            failures.append((path, f'gate: {problems[0][:90]}'))
            continue
        try:
            compile_file_to_wasm(src)
            compiled += 1
        except Exception as exc:                                    # noqa: BLE001
            failures.append((path, f'compile: {type(exc).__name__}: {str(exc)[:90]}'))
            continue
        try:
            if from_binary(to_binary(ast)) is not None:
                roundtrip += 1
        except Exception as exc:                                    # noqa: BLE001
            failures.append((path, f'roundtrip: {type(exc).__name__}: {str(exc)[:90]}'))

    print(f'files={total} compiled={compiled} refused={refused} '
          f'ai_findings={ai_findings} roundtrip={roundtrip}')
    for path, why in failures:
        print(f'  {os.path.relpath(path, ROOT)}: {why}')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
