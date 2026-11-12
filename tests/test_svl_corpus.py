"""Corpus regression: every compilable program must round-trip, and the gate and the
abstract interpreter must stay silent on this corpus.

The corpus is the workspace `*.svl` files plus `svl-release/examples/*.svl`. A handful of
legacy fixtures never parsed before this work and still do not; they are excluded by the
"compiled" count rather than by special-casing names.
"""
import pytest

from svl.abstract_interpretation import analyze_program
from svl.compiler_wasm import compile_file_to_wasm
from svl.lexer import tokenize
from svl.parser_rd import parse
from svl.serialization import from_binary, to_binary
from svl.verify_gate import verify_program

CORPUS = [
    # (path, source)
]


def _load_corpus():
    import glob
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Both layouts: the public repo keeps programs in `examples/`; the development
    # workspace keeps them at the repo root and mirrors the public examples under
    # `svl-release/`.
    patterns = [os.path.join(root, "*.svl"),
                os.path.join(root, "svl", "*.svl"),
                os.path.join(root, "examples", "*.svl"),
                os.path.join(root, "svl-release", "examples", "*.svl")]
    seen, out = set(), []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            out.append((path, open(path, encoding="utf-8").read()))
    return out


def test_corpus_compiles_and_roundtrips():
    programs = _load_corpus()
    assert len(programs) >= 20, f"corpus shrank: {len(programs)} files"

    compiled = refused = ai_findings = roundtrips = 0
    failures = []
    for path, source in programs:
        try:
            ast = parse(tokenize(source))
        except SyntaxError:
            continue
        ai = analyze_program(ast)
        ai_findings += len(ai.findings)
        problems = verify_program(source)
        if problems:
            refused += 1
            failures.append((path, problems[0]))
            continue
        try:
            compile_file_to_wasm(source)
            compiled += 1
        except Exception as exc:                                # noqa: BLE001
            failures.append((path, f"{type(exc).__name__}: {exc}"))
            continue
        assert from_binary(to_binary(ast)) is not None, path
        roundtrips += 1

    assert ai_findings == 0, f"abstract interpreter findings: {ai_findings}"
    assert refused == 0, f"gate refusals: {failures}"
    assert compiled >= 19, f"only {compiled} programs compiled"
    assert roundtrips == compiled
