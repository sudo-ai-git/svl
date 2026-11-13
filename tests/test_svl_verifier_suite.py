"""P1.5 — the labeled verifier corpus and its kill-switches.

The corpus asserts the whole verdict against a human label (must-refuse / must-pass).
The kill-switches disable one check at a time and require the corpus to NOTICE: a corpus
that still passes with a check disabled is decoration, not a gate.
"""
import pytest

from svl.compiler_wasm import compile_file_to_wasm
from svl.verify_gate import SVLVerificationError
from svl.verifier_suite import (
    MUST_PASS, MUST_REFUSE, check, kill_switch_interval_ai, kill_switch_type_checker,
    run_suite,
)


def test_corpus_is_balanced_and_non_empty():
    assert len(MUST_REFUSE) >= 20
    assert len(MUST_PASS) >= 20
    # every label must be a distinct program
    assert set(MUST_REFUSE).isdisjoint(MUST_PASS)


def test_every_label_agrees_with_the_verifier():
    failures = run_suite()
    assert failures == [], f"{len(failures)} label disagreements: {failures}"


def test_must_refuse_programs_are_actually_refused():
    for name, src in MUST_REFUSE.items():
        refused, reasons = check(src)
        assert refused, f"{name} should be refused but the verifier was silent"


def test_must_pass_programs_are_actually_silent():
    for name, src in MUST_PASS.items():
        refused, reasons = check(src)
        assert not refused, f"{name} should pass but was refused: {reasons[:1]}"


def test_kill_switch_type_checker_is_noticed():
    """Disabling the let-type check must make the corpus fail."""
    failures = kill_switch_type_checker()
    assert failures, "the corpus did not notice a disabled type checker"


def test_kill_switch_interval_ai_is_noticed():
    """Disabling the interval analyser must make the corpus fail."""
    failures = kill_switch_interval_ai()
    assert failures, "the corpus did not notice a disabled interval analyser"


def test_unknown_call_is_refused_by_the_gate():
    """An unknown callee is an unknown identifier, not a void-typed call."""
    src = "module m { func main() type int { return nope(1) } }"
    with pytest.raises(SVLVerificationError, match="unknown function 'nope'"):
        compile_file_to_wasm(src)


def test_imported_names_resolve_in_the_linked_program(tmp_path):
    """The gate verifies the LINKED program, so a cross-module call is not 'unknown'."""
    (tmp_path / "lib.svl").write_text(
        "module lib { func answer() type int { return 42 } }")
    main = 'import "lib.svl"\nmodule m { func main() type int { return answer() } }'
    compile_file_to_wasm(main, base_dir=str(tmp_path))     # must not raise
