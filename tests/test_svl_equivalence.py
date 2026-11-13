"""P2.2 — SMT equivalence checking.

`DifferentialVerifier` compares layer verdicts, so `a + 2` / `a - 2` / `a * 2` all look
identical.  This module refutes `f(x) != g(x)` in Z3: unsat means the functions are
equivalent for every modelled input, sat means the model is a concrete counterexample.
"""
import pytest

from svl.equivalence import prove_equivalent
from svl.cli import main as cli_main


def _fn(body: str, name: str = "f", params: str = "a: int, b: int",
        ret: str = "int") -> str:
    return f"module m {{ func {name}({params}) type {ret} {{ {body} }} }}"


def test_commutative_addition_is_proven_equivalent():
    result = prove_equivalent(_fn("return a + b"), _fn("return b + a", name="g"))
    assert result.status == "proven"


def test_associative_grouping_is_proven_equivalent():
    result = prove_equivalent(
        "module m { func f(a: int, b: int, c: int) type int { return (a + b) + c } }",
        "module m { func g(a: int, b: int, c: int) type int { return a + (b + c) } }")
    assert result.status == "proven"


def test_let_binding_is_proven_equivalent():
    result = prove_equivalent(
        _fn("let b = a * 2 return b + 1"),
        _fn("return a * 2 + 1", name="g"))
    assert result.status == "proven"


def test_if_else_rewrite_is_proven_equivalent():
    result = prove_equivalent(
        "module m { func f(a: int) type int { if a > 0 then { return a } "
        "else { return -a } } }",
        "module m { func g(a: int) type int { if a > 0 then { return a } "
        "else { return 0 - a } } }")
    assert result.status == "proven"


def test_a_changed_operator_is_refuted_with_a_counterexample():
    result = prove_equivalent(_fn("return a + b"), _fn("return a - b", name="g"))
    assert result.status == "counterexample"
    assert result.counterexample is not None
    # b must be non-zero; a is unconstrained and reported as such
    assert result.counterexample.get("b") not in (None, 0, "any")
    assert result.counterexample.get("a") == "any"


def test_a_loop_is_declined_not_mis_modelled():
    loop = ("module m { func f(a: int) type int { let s = 0 for i in 0..a { s += i } "
            "return s } }")
    result = prove_equivalent(loop, _fn("return a", name="g", params="a: int"))
    assert result.status == "unverified"


def test_signature_mismatch_is_reported():
    result = prove_equivalent(_fn("return a"),
                              "module m { func g(a: int) type string { return \"x\" } }")
    assert result.status == "signature-mismatch"


def test_cli_diff(tmp_path):
    a = tmp_path / "a.svl"
    b = tmp_path / "b.svl"
    a.write_text(_fn("return a + b"))
    b.write_text(_fn("return b + a", name="g"))
    assert cli_main(["diff", str(a), str(b)]) == 0
